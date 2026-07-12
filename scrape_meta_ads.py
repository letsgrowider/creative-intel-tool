import os
import re
import time
import requests

_BASE = "https://graph.facebook.com/v21.0"


def _get_token() -> str:
    return os.environ["META_ACCESS_TOKEN"]


def _page_id_from_url(url: str, token: str) -> str:
    """Resolve a Facebook page URL or profile URL to its numeric page ID."""
    # Already a numeric ID in profile.php?id=xxxx
    m = re.search(r'[?&]id=(\d+)', url)
    if m:
        return m.group(1)

    # Extract the last path segment as the page slug
    slug = re.split(r'[/?#]', url.rstrip('/').split('facebook.com/')[-1])[0]
    if not slug:
        raise ValueError(f"Cannot extract page slug from URL: {url}")

    resp = requests.get(
        f"{_BASE}/{slug}",
        params={"fields": "id,name", "access_token": token},
        timeout=15,
    )
    data = resp.json()
    if "id" in data:
        print(f"[META API] Resolved '{slug}' → page ID {data['id']} ({data.get('name','')})")
        return data["id"]
    raise ValueError(f"Could not resolve page ID for '{slug}': {data.get('error', data)}")


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


def _fetch_page_ads(page_id: str, token: str, max_ads: int, countries: list[str]) -> list[dict]:
    """Call ads_archive for one page, paginating until max_ads reached."""
    ads: list[dict] = []
    params: dict = {
        "access_token": token,
        "ad_reached_countries": str(countries).replace("'", '"'),
        "search_page_ids": page_id,
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
    if countries is None:
        countries = ["IN"]

    token    = _get_token()
    all_ads: list[dict] = []
    seen:    set[str]   = set()

    for url in page_urls:
        print(f"[META API] Resolving {url} ...")
        try:
            page_id = _page_id_from_url(url, token)
        except Exception as exc:
            print(f"[META API] Skipping {url}: {exc}")
            continue

        print(f"[META API] Fetching ads for page {page_id} ...")
        try:
            raw_ads = _fetch_page_ads(page_id, token, max_ads, countries)
        except Exception as exc:
            print(f"[META API] Error for {url}: {exc}")
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
    return all_ads


if __name__ == "__main__":
    import json
    ads = scrape_meta_ads(["https://www.facebook.com/vasudhafoodsofficial"], max_ads=5)
    print(json.dumps(ads[:2], indent=2, default=str))
