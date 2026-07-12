import os
import time
import requests

ACTOR_ID = "apify~facebook-ads-scraper"
BASE_URL = "https://api.apify.com/v2"


def _start_run(page_urls: list[str], max_ads: int) -> str:
    APIFY_TOKEN = os.environ["APIFY_API_TOKEN"]
    payload = {
        "startUrls": [{"url": u} for u in page_urls],
        "maxAds": max_ads,
    }
    resp = requests.post(
        f"{BASE_URL}/acts/{ACTOR_ID}/runs",
        params={"token": APIFY_TOKEN},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def _poll_run(run_id: str, poll_interval: int = 10, timeout: int = 600) -> None:
    APIFY_TOKEN = os.environ["APIFY_API_TOKEN"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(
            f"{BASE_URL}/actor-runs/{run_id}",
            params={"token": APIFY_TOKEN},
            timeout=30,
        )
        resp.raise_for_status()
        status = resp.json()["data"]["status"]
        if status == "SUCCEEDED":
            return
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Apify run {run_id} ended with status: {status}")
        time.sleep(poll_interval)
    raise TimeoutError(f"Apify run {run_id} did not finish within {timeout}s")


def _fetch_results(run_id: str) -> list[dict]:
    APIFY_TOKEN = os.environ["APIFY_API_TOKEN"]
    resp = requests.get(
        f"{BASE_URL}/actor-runs/{run_id}/dataset/items",
        params={"token": APIFY_TOKEN, "format": "json"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _normalize(ad: dict) -> dict | None:
    card = {}
    try:
        card = ad.get("snapshot", {}).get("cards", [{}])[0]
    except (IndexError, AttributeError):
        pass

    video_url = card.get("videoHdUrl") or card.get("videoSdUrl")
    image_url = card.get("originalImageUrl") or card.get("resizedImageUrl")
    media_url = video_url or image_url
    media_type = "video" if video_url else "image"

    return {
        "adArchiveId": ad.get("adArchiveId"),
        "pageName": ad.get("pageName"),
        "startDate": ad.get("startDate"),
        "publisherPlatform": ad.get("publisherPlatform"),
        "body": card.get("body"),
        "ctaText": card.get("ctaText"),
        "title": card.get("title"),
        "linkUrl": card.get("linkUrl"),
        "mediaUrl": media_url,
        "media_type": media_type,
    }


def scrape_meta_ads(page_urls: list[str], max_ads: int = 50) -> list[dict]:
    """
    Scrape competitor ads from Meta Ad Library via Apify.

    Args:
        page_urls: Facebook page URLs, e.g. ["https://www.facebook.com/drinkAG1"]
        max_ads:   Max ads to fetch per page (default 50).

    Returns:
        Deduplicated, oldest-first list of normalized ad dicts.
    """
    run_id = _start_run(page_urls, max_ads)
    _poll_run(run_id)
    raw = _fetch_results(run_id)

    normalized = [_normalize(ad) for ad in raw]
    normalized = [ad for ad in normalized if ad is not None]

    # Deduplicate by media URL; keep first occurrence
    seen: set[str | None] = set()
    deduped = []
    for ad in normalized:
        key = ad["mediaUrl"]
        if key not in seen:
            seen.add(key)
            deduped.append(ad)

    # Sort oldest first (longest-running = likely winners)
    deduped.sort(key=lambda a: a["startDate"] or "")

    return deduped


if __name__ == "__main__":
    import json

    results = scrape_meta_ads(
        page_urls=["https://www.facebook.com/drinkAG1"],
        max_ads=20,
    )
    print(json.dumps(results, indent=2))
