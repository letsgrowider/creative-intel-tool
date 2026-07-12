import os
import time
import mimetypes
from pathlib import Path

from google import genai
from google.genai import types

ANALYSES_DIR = "analyses"
MODEL = "gemini-2.5-flash"

def _get_client():
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _analysis_prompt(ad: dict) -> str:
    return f"""You are an expert performance creative strategist analyzing a competitor ad from the Meta Ad Library.

AD METADATA:
- Brand: {ad.get('pageName')}
- Ad Archive ID: {ad.get('adArchiveId')}
- Start Date: {ad.get('startDate')}
- Platforms: {ad.get('publisherPlatform')}
- Title: {ad.get('title')}
- Ad Copy: {ad.get('body')}
- CTA Text: {ad.get('ctaText')}
- Link URL: {ad.get('linkUrl')}
- Media Type: {ad.get('media_type')}

Analyze this ad across the following 7 dimensions. Be specific and tactical — avoid generic observations.

---

## 1. Hook
{"For this VIDEO ad: Describe the opening visual (first 0–3 seconds), any text overlay, any spoken line. Identify the hook type: curiosity gap / bold claim / problem callout / social proof / pattern interrupt / before-after / question." if ad.get('media_type') == 'video' else "For this IMAGE ad: Describe the primary scroll-stopping visual element and any text overlay. Identify the hook type: curiosity gap / bold claim / problem callout / social proof / pattern interrupt / before-after / question."}

## 2. Angle
What specific pain point or desire is this targeting? What is the core argument or unique mechanism being sold? Who is the implied audience?

## 3. Visual Format
What is the overall format? (e.g. talking head, UGC, product demo, lifestyle, split screen, text-on-screen, static product, infographic, testimonial, etc.)
What is the production quality level (lo-fi / mid / polished)? Describe the pacing and visual rhythm.

## 4. Copy Framework
How does the copy open and close? What proof elements are used (stats, testimonials, credentials, social proof, guarantees)? What is the narrative structure?

## 5. CTA Approach
What is the call to action? How is urgency or scarcity created (if at all)? How is the offer framed?

## 6. Emotional Trigger
What is the primary emotion being leveraged? (e.g. fear, aspiration, FOMO, curiosity, validation, trust, guilt, excitement) How specifically is it activated?

## 7. Audience Signal
Who is this clearly targeting? List the specific lifestyle markers, vocabulary choices, or visual cues that signal the target demographic/psychographic.

---

## Primary Performance Driver
Single most likely reason this ad is a winner. One punchy sentence.

## Portable Mechanic
The structural or conceptual element that could be lifted and adapted for a completely different brand or category. Be specific — name the mechanic and explain how to reuse it.
"""


def _upload_video(local_path: str) -> types.File:
    client = _get_client()
    mime = mimetypes.guess_type(local_path)[0] or "video/mp4"
    uploaded = client.files.upload(
        file=local_path,
        config=types.UploadFileConfig(mime_type=mime),
    )
    while uploaded.state.name == "PROCESSING":
        time.sleep(5)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state.name != "ACTIVE":
        raise RuntimeError(f"File {uploaded.name} failed processing: {uploaded.state.name}")
    return uploaded


def _analyze_video(ad: dict) -> str:
    client = _get_client()
    uploaded = _upload_video(ad["localPath"])
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_uri(file_uri=uploaded.uri, mime_type=uploaded.mime_type),
                _analysis_prompt(ad),
            ],
        )
    finally:
        client.files.delete(name=uploaded.name)
    return response.text


def _analyze_image(ad: dict) -> str:
    client = _get_client()
    image_bytes = Path(ad["localPath"]).read_bytes()
    mime = mimetypes.guess_type(ad["localPath"])[0] or "image/jpeg"
    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            _analysis_prompt(ad),
        ],
    )
    return response.text


def _analyze_text(ad: dict) -> str:
    client = _get_client()
    copy = ad.get("ad_copy_full") or ad.get("body") or ""
    prompt = (
        _analysis_prompt(ad)
        + f"\n\nAD COPY (full text — no visual media available):\n{copy}\n\n"
        "Note: No visual media is available. Base your visual format and hook analysis "
        "on the copy text, context clues, and any metadata provided."
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=[prompt],
    )
    return response.text


def _write_analysis(ad: dict, analysis_text: str, analyses_dir: str) -> str:
    header = f"""---
brand: {ad.get('pageName')}
adArchiveId: {ad.get('adArchiveId')}
mediaType: {ad.get('media_type')}
startDate: {ad.get('startDate')}
platforms: {ad.get('publisherPlatform')}
adCopy: |
  {(ad.get('body') or '').replace(chr(10), chr(10) + '  ')}
---

"""
    content = header + analysis_text
    Path(analyses_dir).mkdir(parents=True, exist_ok=True)

    brand = (ad.get("pageName") or "unknown").replace(" ", "_")
    filename = f"{brand}_{ad.get('adArchiveId')}.md"
    dest = os.path.join(analyses_dir, filename)
    Path(dest).write_text(content, encoding="utf-8")
    return dest


def analyze_ads_gemini(
    ads: list[dict],
    base_dir: str = ".",
) -> list[dict]:
    """
    Analyze each ad with Gemini 2.5 Flash and save markdown reports.

    Args:
        ads:      List of normalized ad dicts with 'localPath' set.
        base_dir: Root directory for analyses/ folder.

    Returns:
        Same list with 'analysisPath' key added (None on failure/skip).
    """
    analyses_dir = os.path.join(base_dir, ANALYSES_DIR)

    for ad in ads:
        brand = (ad.get("pageName") or "unknown").replace(" ", "_")
        filename = f"{brand}_{ad.get('adArchiveId')}.md"
        dest = os.path.join(analyses_dir, filename)

        if os.path.exists(dest):
            print(f"[SKIP] {filename} already exists")
            ad["analysisPath"] = dest
            continue

        local_path = ad.get("localPath")
        has_media  = local_path and os.path.exists(local_path)

        if not has_media and not ad.get("ad_copy_full") and not ad.get("body"):
            print(f"[SKIP] {ad.get('adArchiveId')} — no media and no copy text")
            ad["analysisPath"] = None
            continue

        try:
            if has_media:
                print(f"[ANALYZE] {ad.get('media_type').upper()} — {filename}")
                if ad.get("media_type") == "video":
                    analysis = _analyze_video(ad)
                else:
                    analysis = _analyze_image(ad)
            else:
                print(f"[ANALYZE] TEXT-ONLY — {filename}")
                analysis = _analyze_text(ad)

            path = _write_analysis(ad, analysis, analyses_dir)
            ad["analysisPath"] = path
            print(f"[DONE] Saved -> {path}")

        except Exception as e:
            print(f"[ERROR] {ad.get('adArchiveId')}: {e}")
            ad["analysisPath"] = None

    return ads


if __name__ == "__main__":
    from scrape_meta_ads import scrape_meta_ads
    from download_ad_media import download_ad_media

    ads = scrape_meta_ads(["https://www.facebook.com/drinkAG1"], max_ads=5)
    ads = download_ad_media(ads)
    ads = analyze_ads_gemini(ads)

    for ad in ads:
        print(ad["adArchiveId"], "->", ad.get("analysisPath"))
