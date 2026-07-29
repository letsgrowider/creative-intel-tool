import os
import re
import time
import requests

_BASE = "https://graph.facebook.com/v21.0"


def _get_token() -> str:
    return os.environ["META_ACCESS_TOKEN"]


def _slug_from_url(url: str) -> str:
    path = url.rstrip('/').split('facebook.com/')[-1]
    return re.split(r'[/?#]', path)[0]


def _page_id_from_url(url: str) -> tuple[str | None, str]:
    """
    Return (page_id, slug).
    - Numeric profile.php?id=xxx → page_id directly
    - Slug-based → None, slug (caller resolves via _resolve_page_id)
    """
    m = re.search(r'[?&]id=(\d+)', url)
    if m:
        return m.group(1), ""

    slug = _slug_from_url(url)
    if not slug:
        raise ValueError(f"Cannot parse URL: {url}")

    return None, slug


def _slug_normalize(s: str) -> str:
    """Lowercase, strip extensions and punctuation → compact string for matching."""
    s = s.lower()
    for ext in ('.in', '.com', '.net', '.org'):
        s = s.replace(ext, '')
    return re.sub(r'[^a-z0-9]', '', s)


def _page_matches_slug(page_name: str, slug: str) -> bool:
    """True if page_name and slug share substantial overlap when normalized."""
    slug_n = _slug_normalize(slug)
    name_n = _slug_normalize(page_name)
    # direct containment (e.g. slug="axisbank", name="axisbank" or "axis bank")
    if name_n and (slug_n in name_n or name_n in slug_n):
        return True
    # partial: slug without banking noise words matches start of page name
    banking_words = ('bank', 'india', 'sfb', 'limited', 'ltd', 'finance')
    slug_core = re.sub(r'(' + '|'.join(banking_words) + r')', '', slug_n)
    if len(slug_core) >= 2 and name_n.startswith(slug_core):
        # if the original slug mentioned 'bank', page must also be a bank
        if 'bank' in slug_n and 'bank' not in name_n:
            return False
        return True
    return False


def _humanize_slug(slug: str) -> str:
    """bandhanbank.in → 'Bandhan Bank', aubankindia → 'Au Bank India'"""
    s = slug.lower()
    for ext in ('.in', '.com', '.net', '.org'):
        s = s.replace(ext, '')
    s = re.sub(r'(bank|india|sfb|limited|ltd)', r' \1', s).strip()
    return s.title()


def _resolve_page_id(slug: str, token: str) -> str | None:
    """
    Two-pass: try multiple search terms derived from slug, find the ad-archive
    page whose normalized name best matches the slug.
    """
    search_attempts = list(dict.fromkeys([slug, _humanize_slug(slug)]))

    for term in search_attempts:
        try:
            resp = requests.get(
                f"{_BASE}/ads_archive",
                params={
                    "access_token": token,
                    "search_terms": term,
                    "ad_reached_countries": '["IN","US","GB","AU"]',
                    "fields": "id,page_name,page_id",
                    "limit": 50,
                },
                timeout=30,
            )
            data = resp.json()
            if "error" in data:
                continue

            candidates: dict[str, str] = {}
            for ad in data.get("data", []):
                pid = ad.get("page_id")
                pname = ad.get("page_name") or ""
                if pid and _page_matches_slug(pname, slug):
                    candidates[pid] = pname

            if candidates:
                page_id, page_name = next(iter(candidates.items()))
                print(f"[META API] Resolved '{slug}' → '{page_name}' (id={page_id})")
                return page_id

        except Exception as e:
            print(f"[META API] resolution attempt '{term}' failed: {e}")

    return None


def _fetch_ads(token: str, max_ads: int, countries: list[str],
               page_id: str | None = None, search_terms: str | None = None) -> list[dict]:
    if not page_id and not search_terms:
        raise ValueError("Need page_id or search_terms")

    ads: list[dict] = []
    params: dict = {
        "access_token": token,
        "ad_reached_countries": str(countries).replace("'", '"'),
        "fields": ",".join([
            "id", "page_name", "page_id",
            "ad_creative_bodies",
            "ad_creative_link_captions",
            "ad_creative_link_descriptions",
            "ad_creative_link_titles",
            "ad_creative_link_url",
            "ad_delivery_start_time",
            "publisher_platforms",
        ]),
        "limit": min(max_ads, 100),
    }
    if page_id:
        params["search_page_ids"] = page_id
    else:
        params["search_terms"] = search_terms

    while len(ads) < max_ads:
        resp = requests.get(f"{_BASE}/ads_archive", params=params, timeout=30)
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"Meta API error: {data['error']}")

        batch = data.get("data", [])
        ads.extend(batch)

        cursor = data.get("paging", {}).get("cursors", {}).get("after")
        if not cursor or not batch:
            break
        params["after"] = cursor

    return ads[:max_ads]


def _normalize(raw: dict) -> dict:
    bodies = raw.get("ad_creative_bodies") or []
    titles = raw.get("ad_creative_link_titles") or []
    descs  = raw.get("ad_creative_link_descriptions") or []
    caps   = raw.get("ad_creative_link_captions") or []

    body  = bodies[0] if bodies else ""
    title = titles[0] if titles else ""
    desc  = descs[0]  if descs  else ""
    cap   = caps[0]   if caps   else ""

    return {
        "adArchiveId":       raw.get("id", ""),
        "pageName":          raw.get("page_name", ""),
        "startDate":         raw.get("ad_delivery_start_time", ""),
        "publisherPlatform": raw.get("publisher_platforms", []),
        "body":              body,
        "ctaText":           cap,
        "title":             title,
        "linkUrl":           raw.get("ad_creative_link_url", ""),
        "mediaUrl":          "",
        "media_type":        "text",
        "ad_copy_full":      "\n".join(filter(None, [body, title, desc, cap])),
    }


def scrape_meta_ads(
    page_urls: list[str],
    max_ads: int = 25,
    countries: list[str] | None = None,
) -> list[dict]:
    if countries is None:
        countries = ["IN", "US", "GB", "AU", "CA", "SG", "AE", "ZA"]

    token    = _get_token()
    all_ads: list[dict] = []
    seen:    set[str]   = set()
    errors:  list[str]  = []

    for url in page_urls:
        try:
            page_id, slug = _page_id_from_url(url)
        except Exception as exc:
            errors.append(str(exc))
            continue

        # For slug-based URLs, try to resolve to a page_id for exact results
        if not page_id and slug:
            resolved = _resolve_page_id(slug, token)
            if resolved:
                page_id = resolved

        label = f"page ID {page_id}" if page_id else f"name '{slug}'"
        print(f"[META API] Fetching ads for {label} ...")

        try:
            raw_ads = _fetch_ads(
                token, max_ads, countries,
                page_id=page_id,
                search_terms=slug if not page_id else None,
            )
        except Exception as exc:
            msg = f"API error for {url}: {exc}"
            print(f"[META API] {msg}")
            errors.append(msg)
            continue

        print(f"[META API] {len(raw_ads)} ads from {label}")
        for raw in raw_ads:
            ad_id = raw.get("id", "")
            if ad_id in seen:
                continue
            seen.add(ad_id)
            all_ads.append(_normalize(raw))

    all_ads.sort(key=lambda a: a.get("startDate") or "")
    print(f"[META API] Done — {len(all_ads)} unique ads total")

    if not all_ads and errors:
        raise RuntimeError("No ads found. Errors:\n" + "\n".join(errors))
    return all_ads


if __name__ == "__main__":
    import json
    ads = scrape_meta_ads(["https://www.facebook.com/vasudhafoodsofficial"], max_ads=5)
    print(json.dumps(ads[:2], indent=2, default=str))
