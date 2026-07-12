import os
import re
import requests

VIDEOS_DIR = "videos"
IMAGES_DIR = "images"


def _safe_brand(page_name: str) -> str:
    return re.sub(r"[^\w]", "", page_name.replace(" ", "_"))


def _ensure_dirs() -> None:
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)


def _download(url: str, dest: str) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def download_ad_media(ads: list[dict], base_dir: str = ".") -> list[dict]:
    """
    Download media for each ad dict (output of scrape_meta_ads).

    Args:
        ads:      List of normalized ad dicts.
        base_dir: Root directory for videos/ and images/ folders.

    Returns:
        Same list with a "localPath" key added (None if no media URL).
    """
    videos_path = os.path.join(base_dir, VIDEOS_DIR)
    images_path = os.path.join(base_dir, IMAGES_DIR)
    os.makedirs(videos_path, exist_ok=True)
    os.makedirs(images_path, exist_ok=True)

    for ad in ads:
        media_url = ad.get("mediaUrl")
        if not media_url:
            ad["localPath"] = None
            continue

        brand = _safe_brand(ad.get("pageName") or "unknown")
        archive_id = ad.get("adArchiveId") or "noId"
        ext = "mp4" if ad.get("media_type") == "video" else "jpg"
        folder = videos_path if ext == "mp4" else images_path
        filename = f"{brand}_{archive_id}.{ext}"
        dest = os.path.join(folder, filename)

        if os.path.exists(dest):
            ad["localPath"] = dest
            continue

        try:
            _download(media_url, dest)
            ad["localPath"] = dest
        except Exception as e:
            print(f"[WARN] Failed to download {archive_id}: {e}")
            ad["localPath"] = None

    return ads


if __name__ == "__main__":
    import json
    from scrape_meta_ads import scrape_meta_ads

    ads = scrape_meta_ads(["https://www.facebook.com/drinkAG1"], max_ads=10)
    ads = download_ad_media(ads)
    for ad in ads:
        print(ad["adArchiveId"], "->", ad["localPath"])
