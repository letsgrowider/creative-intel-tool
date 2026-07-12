import os
import re
import time
import requests

_BASE = "https://graph.facebook.com/v21.0"


def _get_token() -> str:
    return os.environ["META_ACCESS_TOKEN"]


_FB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_PAGE_ID_PATTERNS = [
    r'"pageID"\s*:\s*"?(\d+)"?',
    r'"page_id"\s*:\s*"?(\d+)"?',
    r'fb://page/(\d+)',
    r'"entity_id"\s*:\s*"(\d+)"',
    r'content="fb://page/\?id=(\d+)"',
]


def _page_id_from_html(fb_url: str) -> str | None:
    """Extract numeric page ID from Facebook page HTML — no API permissions needed."""
    try:
        resp = requests.get(fb_url, headers=_FB_HEADERS, timeout=15)
        html = resp.text
        for pat in _PAGE_ID_PATTERNS:
            m = re.search(pat, html)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def _slug_from_url(url: str) -> str:
    """Extract the page slug (last path segment) from a Facebook URL."""
    path = url.rstrip('/').split('facebook.com/')[-1]
    return re.split(r'[/?#]', path)[0]


def _page_id_from_url(url: str, token: str) -> tuple[str | None, str]:
    """
    Return (page_id, slug). page_id may be None if resolution fails —
    caller should fall back to search_terms using the slug.
    """
    # Numeric ID already in URL (profile.php?id=xxx)
    m = re.search(r'[?&]id=(\d+)', url)
    if m:
        return m.group(1), ""

    slug = _slug_from_url(url)
    if not slug:
        raise ValueError(f"Cannot parse Facebook URL: {url}")

    # Try scraping page HTML for the numeric ID
    page_id = _page_id_from_html(url if "facebook.com" in url else f"https://www.facebook.com/{slug}")
    if page_id:
        print(f"[META API] HTML-resolved '{slug}' → page ID {page_id}")
        return page_id, slug

    # Try Graph API (works only if app has pages_read_engagement)
    try:
        resp = requests.get(
            f"{_BASE}/{slug}",
            params={"fields": "id,name", "access_token": token},
            timeout=15,
        )
        data = resp.json()
        if "id" in data:
            print(f"[META API] Graph-resolved '{slug}' → page ID {data['id']}")
            return data["id"], slug
    except Exception:
        pass

    # Fall back — caller will use search_terms instead
    print(f"[META API] Could not resolve page ID for '{slug}', will search by name")
    return None, slug


def _extract_image_from_snapshot(snapshot_url: str) -> str | None:
    """Parse the ad snapshot page for a CDN image URL."""
    try:
        resp = requests.get(snapshot_url, timeout=15)
        html = resp.text
        # og:image is most reliable
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
        if m:
            return m.group(1).replace("&amp;", "&")
        # fallback: fbcdn image tag
        m = re.search(r'<img[^>]+src=["\']([^"\']*fbcdn\.net[^"\']+)["\']', html)
        if m:
            return m.group(1).replace("&amp;", "&")
    except Exception:
        pass
    return None


def _fetch_ads(token: str, max_ads: int, countries: list[str],
               page_id: str | None = None, search_terms: str | None = None) -> list[dict]:
    """Call ads_archive by page_id or search_terms, paginating until max_ads."""
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
            "ad_snapshot_url",
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
    """Convert a raw ads_archive item to our standard ad dict."""
    bodies = raw.get("ad_creative_bodies") or []
    titles = raw.get("ad_creative_link_titles") or []
    descs  = raw.get("ad_creative_link_descriptions") or []
    caps   = raw.get("ad_creative_link_captions") or []

    body  = bodies[0] if bodies else ""
    title = titles[0] if titles else ""
    desc  = descs[0]  if descs  else ""
    cap   = caps[0]   if caps   else ""

    snapshot_url = raw.get("ad_snapshot_url", "")
    media_url    = _extract_image_from_snapshot(snapshot_url) if snapshot_url else ""
    media_type   = "image" if media_url else "text"

    return {
        "adArchiveId":       raw.get("id", ""),
        "pageName":          raw.get("page_name", ""),
        "startDate":         raw.get("ad_delivery_start_time", ""),
        "publisherPlatform": raw.get("publisher_platforms", []),
        "body":              body,
        "ctaText":           cap,
        "title":             title,
        "linkUrl":           raw.get("ad_creative_link_url", ""),
        "mediaUrl":          media_url,
        "media_type":        media_type,
        "snapshot_url":      snapshot_url,
        "ad_copy_full":      "\n".join(filter(None, [body, title, desc, cap])),
    }


def scrape_meta_ads(
    page_urls: list[str],
    max_ads: int = 25,
    countries: list[str] | None = None,
) -> list[dict]:
    """
    Fetch ads for one or more Facebook pages via the Meta Ad Library API.

    Args:
        page_urls: List of Facebook page URLs (slug or profile.php?id=xxx).
        max_ads:   Max ads to fetch per page.
        countries: Country codes to filter by. Defaults to ["IN"].

    Returns:
        Normalised, deduplicated ad dicts sorted oldest-first.
    """
    # Broad default — catches ads running in any major market
    if countries is None:
        countries = ["IN", "US", "GB", "AU", "CA", "SG", "AE", "ZA"]

    token    = _get_token()
    all_ads: list[dict] = []
    seen:    set[str]   = set()
    errors:  list[str]  = []

    for url in page_urls:
        print(f"[META API] Resolving {url} ...")
        try:
            page_id, slug = _page_id_from_url(url, token)
        except Exception as exc:
            msg = f"Cannot parse URL {url}: {exc}"
            print(f"[META API] {msg}")
            errors.append(msg)
            continue

        label = f"page {page_id}" if page_id else f"search '{slug}'"
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

        print(f"[META API] {len(raw_ads)} ads — normalising & extracting media ...")
        for raw in raw_ads:
            ad_id = raw.get("id", "")
            if ad_id in seen:
                continue
            seen.add(ad_id)
            all_ads.append(_normalize(raw))
            time.sleep(0.15)

    all_ads.sort(key=lambda a: a.get("startDate") or "")
    print(f"[META API] Done — {len(all_ads)} unique ads total")
    if not all_ads and errors:
        raise RuntimeError("No ads found. Errors:\n" + "\n".join(errors))
    return all_ads


if __name__ == "__main__":
    import json
    ads = scrape_meta_ads(["https://www.facebook.com/vasudhafoodsofficial"], max_ads=5)
    print(json.dumps(ads[:2], indent=2, default=str))
