import os
import re
import glob
from datetime import date
from pathlib import Path

import anthropic

OUTPUT_DIR = "output"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16000

def _get_claude():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _extract_section(text: str, heading: str) -> str:
    """Pull content between two ## headings."""
    pattern = rf"## {re.escape(heading)}\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        return ""
    # First non-empty line only — enough signal, cuts verbosity
    lines = [l.strip() for l in m.group(1).strip().splitlines() if l.strip()]
    return lines[0] if lines else ""


def _compress_analysis(stem: str, content: str) -> str:
    """Reduce a full analysis to a compact ~150-token signal block."""
    # Pull YAML frontmatter fields
    brand = re.search(r"^brand:\s*(.+)$", content, re.MULTILINE)
    ad_id = re.search(r"^adArchiveId:\s*(.+)$", content, re.MULTILINE)
    media = re.search(r"^mediaType:\s*(.+)$", content, re.MULTILINE)
    start = re.search(r"^startDate:\s*(.+)$", content, re.MULTILINE)
    copy_block = re.search(r"^adCopy:\s*\|\n(.*?)^---", content, re.MULTILINE | re.DOTALL)

    ad_copy = ""
    if copy_block:
        ad_copy = " ".join(copy_block.group(1).strip().splitlines()).strip()[:200]

    hook      = _extract_section(content, "1. Hook")
    angle     = _extract_section(content, "2. Angle")
    fmt       = _extract_section(content, "3. Visual Format")
    copy_fw   = _extract_section(content, "4. Copy Framework")
    cta       = _extract_section(content, "5. CTA Approach")
    emotion   = _extract_section(content, "6. Emotional Trigger")
    audience  = _extract_section(content, "7. Audience Signal")
    driver    = _extract_section(content, "Primary Performance Driver")
    mechanic  = _extract_section(content, "Portable Mechanic")

    return (
        f"[{brand.group(1).strip() if brand else '?'} | {ad_id.group(1).strip() if ad_id else stem} | "
        f"{media.group(1).strip() if media else '?'} | start:{start.group(1).strip() if start else '?'}]\n"
        f"Copy: {ad_copy}\n"
        f"Hook: {hook}\n"
        f"Angle: {angle}\n"
        f"Format: {fmt}\n"
        f"CopyFW: {copy_fw}\n"
        f"CTA: {cta}\n"
        f"Emotion: {emotion}\n"
        f"Audience: {audience}\n"
        f"Driver: {driver}\n"
        f"Mechanic: {mechanic}"
    )


def _load_analyses(base_dir: str) -> list[tuple[str, str]]:
    pattern = os.path.join(base_dir, "analyses", "*.md")
    paths = sorted(glob.glob(pattern))
    result = []
    for p in paths:
        stem = Path(p).stem
        content = Path(p).read_text(encoding="utf-8")
        result.append((stem, _compress_analysis(stem, content)))
    return result


def _load_brand_voice(base_dir: str) -> str | None:
    for name in ("brand-voice.md", "brand_voice.md"):
        p = os.path.join(base_dir, name)
        if os.path.exists(p):
            return Path(p).read_text(encoding="utf-8")
    return None


def _extract_meta(ads: list[dict]) -> tuple[set[str], int]:
    brands = {ad.get("pageName") for ad in ads if ad.get("pageName")}
    return brands, len(ads)


def _build_prompt(
    analyses: list[tuple[str, str]],
    brand_voice: str | None,
    competitors: set[str],
    total_ads: int,
) -> str:
    sections = []

    sections.append(
        f"You are a senior performance creative strategist.\n\n"
        f"Below are AI-generated breakdowns of {total_ads} competitor ads "
        f"from the following brands: {', '.join(sorted(competitors))}.\n\n"
        f"Each analysis covers hook, angle, visual format, copy framework, CTA, "
        f"emotional trigger, audience signals, primary performance driver, and portable mechanic."
    )

    if brand_voice:
        sections.append(
            "## BRAND VOICE (apply to all ad concepts)\n\n"
            + brand_voice
            + "\n\nAll 10 ad concepts MUST be written in this brand voice."
        )
    else:
        sections.append(
            "No brand voice file found. Label output as GENERIC — "
            "ad concepts should be adaptable to any brand."
        )

    sections.append("---\n## INDIVIDUAL AD ANALYSES (compressed signals)\n")
    for stem, content in analyses:
        sections.append(content)

    sections.append("""---

Based on all the analyses above, produce a structured creative intelligence report with the following sections. Be specific, tactical, and evidence-backed — cite ad IDs or brand names where relevant.

---

# COMPETITIVE CREATIVE INTELLIGENCE REPORT

## 1. Executive Summary
2–3 sentences on the dominant creative strategy across this competitive landscape. What is the meta-pattern?

## 2. Repeating Hook Structures
Which hook types appear across 3 or more ads? For each:
- Pattern name
- How it manifests across ads (with examples)
- Why it works psychologically
- Confidence level (High / Medium / Low)

## 3. Dominant Visual Formats
Rank all observed formats by frequency. Note any format that is overrepresented.

## 4. Recurring Emotional Triggers
Which emotions are consistently leveraged? How are they activated? Any that are underused (opportunity)?

## 5. Copy Framework Patterns
Structural patterns in ad copy across brands — opening hooks, proof stacking, closing structures. Name the frameworks where recognizable (PAS, AIDA, etc.).

## 6. Overused Angles
What angles, claims, or creative approaches are so saturated they should be avoided? Why are they fatigued?

## 7. Top 3 Portable Mechanics
The 3 highest-confidence structural patterns that can transfer to a different brand. For each:
- Mechanic name
- Source ads it appears in
- How to execute it
- Why it transfers

## 8. 10 Ad Concepts
Generate 10 ready-to-execute ad concepts using the portable mechanics identified above. For each concept:

**Concept [N]: [Name]**
- **Source Mechanic:** [which portable mechanic this uses]
- **Hook (Visual):** [opening image or first 3 seconds of video]
- **Hook (Text Overlay):** [on-screen text]
- **Hook (Spoken/Caption):** [spoken line or caption text — video only, omit for static]
- **Angle:** [pain point or desire being targeted]
- **Visual Format:** [talking head / UGC / product demo / lifestyle / static / etc.]
- **Full Ad Copy:** [complete Facebook ad copy, ready to publish]
- **CTA:** [call to action text and button label]
- **Target Avatar:** [specific person — age, situation, pain, desire]
- **Why It Works:** [1–2 sentences on the performance logic]

---

End of report.
""")

    return "\n\n".join(sections)


def generate_creative_brief(
    ads: list[dict] | None = None,
    base_dir: str = ".",
) -> str:
    """
    Read all analyses, synthesize patterns, generate 10 ad concepts via Claude.

    Args:
        ads:      Optional list of ad dicts (used for competitor/count metadata).
        base_dir: Root directory containing analyses/ and optional brand-voice.md.

    Returns:
        Path to the saved markdown report.
    """
    analyses = _load_analyses(base_dir)
    if not analyses:
        raise ValueError(f"No analysis files found in {base_dir}/analyses/")

    brand_voice = _load_brand_voice(base_dir)

    if ads:
        competitors, total_ads = _extract_meta(ads)
    else:
        # Derive from filenames: Brand_adId.md
        competitors = set()
        for stem, _ in analyses:
            parts = stem.rsplit("_", 1)
            if len(parts) == 2:
                competitors.add(parts[0].replace("_", " "))
        total_ads = len(analyses)

    prompt = _build_prompt(analyses, brand_voice, competitors, total_ads)

    print(f"[CLAUDE] Sending {len(analyses)} analyses (~{len(prompt):,} chars) to {MODEL}...")

    response = _get_claude().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    report_text = response.content[0].text

    today = date.today().isoformat()
    competitors_str = ", ".join(sorted(competitors))
    header = f"""---
date: {today}
competitors: {competitors_str}
totalAds: {total_ads}
brandVoice: {"yes" if brand_voice else "no (generic)"}
model: {MODEL}
---

"""

    output_dir = os.path.join(base_dir, OUTPUT_DIR)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    filename = f"creative-brief_{today}.md"
    dest = os.path.join(output_dir, filename)
    Path(dest).write_text(header + report_text, encoding="utf-8")

    print(f"[DONE] Report saved -> {dest}")
    return dest


if __name__ == "__main__":
    from scrape_meta_ads import scrape_meta_ads
    from download_ad_media import download_ad_media
    from analyze_ads_gemini import analyze_ads_gemini

    ads = scrape_meta_ads(["https://www.facebook.com/drinkAG1"], max_ads=20)
    ads = download_ad_media(ads)
    ads = analyze_ads_gemini(ads)
    path = generate_creative_brief(ads=ads)
    print(f"Brief: {path}")
