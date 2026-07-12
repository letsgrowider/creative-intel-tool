"""
Generates a visual HTML competitive intelligence report via Claude.
Reuses the compressed-analysis approach from generate_creative_brief.py.
"""

import os
import re
import glob
import json
import time
from datetime import date
from pathlib import Path

import anthropic

MODEL = "claude-sonnet-4-6"


def _get_claude():
    return anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        max_retries=6,
        timeout=900.0,
    )


# ── Analysis compression (same as generate_creative_brief.py) ────────────────

def _extract_section(text: str, heading: str) -> str:
    pattern = rf"## {re.escape(heading)}\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        return ""
    lines = [l.strip() for l in m.group(1).strip().splitlines() if l.strip()]
    return lines[0] if lines else ""


def _compress(stem: str, content: str) -> str:
    brand    = re.search(r"^brand:\s*(.+)$", content, re.MULTILINE)
    ad_id    = re.search(r"^adArchiveId:\s*(.+)$", content, re.MULTILINE)
    media    = re.search(r"^mediaType:\s*(.+)$", content, re.MULTILINE)
    start    = re.search(r"^startDate:\s*(.+)$", content, re.MULTILINE)
    cb       = re.search(r"^adCopy:\s*\|\n(.*?)^---", content, re.MULTILINE | re.DOTALL)
    ad_copy  = " ".join((cb.group(1) if cb else "").strip().splitlines()).strip()[:200]

    return (
        f"[{brand.group(1).strip() if brand else '?'} | "
        f"{ad_id.group(1).strip() if ad_id else stem} | "
        f"{media.group(1).strip() if media else '?'} | "
        f"start:{start.group(1).strip() if start else '?'}]\n"
        f"Copy: {ad_copy}\n"
        f"Hook: {_extract_section(content, '1. Hook')}\n"
        f"Angle: {_extract_section(content, '2. Angle')}\n"
        f"Format: {_extract_section(content, '3. Visual Format')}\n"
        f"CopyFW: {_extract_section(content, '4. Copy Framework')}\n"
        f"CTA: {_extract_section(content, '5. CTA Approach')}\n"
        f"Emotion: {_extract_section(content, '6. Emotional Trigger')}\n"
        f"Audience: {_extract_section(content, '7. Audience Signal')}\n"
        f"Driver: {_extract_section(content, 'Primary Performance Driver')}\n"
        f"Mechanic: {_extract_section(content, 'Portable Mechanic')}"
    )


def _load_analyses(base_dir: str) -> list[str]:
    paths = sorted(glob.glob(os.path.join(base_dir, "analyses", "*.md")))
    result = []
    for p in paths:
        stem = Path(p).stem
        content = Path(p).read_text(encoding="utf-8")
        result.append(_compress(stem, content))
    return result


def _extract_meta(ads: list[dict]) -> tuple[set[str], int, int, int]:
    brands  = {a.get("pageName") for a in ads if a.get("pageName")}
    videos  = sum(1 for a in ads if a.get("media_type") == "video")
    images  = sum(1 for a in ads if a.get("media_type") == "image")
    return brands, len(ads), videos, images


JSON_SCHEMA = """
Return ONLY a JSON object — no markdown fences, no prose. Schema:

{
  "executive_summary": "2-3 sentence paragraph",
  "meta_pattern": "4-6 word bold phrase",
  "hook_structures": [
    {"name": str, "count": int, "confidence": "High"|"Medium"|"Low",
     "psychology": str, "examples": [str, str]}
  ],
  "visual_formats": [
    {"name": str, "percentage": int, "note": str}
  ],
  "emotional_triggers": [
    {"name": str, "percentage": int, "activation": str, "is_opportunity": bool}
  ],
  "copy_frameworks": [
    {"name": str, "percentage": int, "description": str, "example": str}
  ],
  "overused_angles": [
    {"name": str, "saturation_pct": int, "avoid_because": str}
  ],
  "portable_mechanics": [
    {"rank": int, "name": str, "source_ads": [str],
     "execution": str, "transfer": str}
  ],
  "ad_concepts": [
    {"n": int, "name": str, "mechanic": str,
     "hook_visual": str, "hook_text": str, "hook_spoken": str|null,
     "angle": str, "format": str, "copy": str,
     "cta": str, "avatar": str, "why": str}
  ]
}

Requirements:
- hook_structures: list all types found (≥3 items)
- visual_formats: percentages must sum to 100
- emotional_triggers: include ALL found + mark underused ones as is_opportunity=true
- ad_concepts: exactly 10 items
- Be specific and cite brand names / ad IDs as evidence
"""


def _call_claude(analyses: list[str], brand_voice: str, competitors: set[str], total: int) -> dict:
    brand_voice_block = (
        f"\n\n## BRAND VOICE TO APPLY\n{brand_voice}\nWrite all 10 ad concepts in this voice.\n"
        if brand_voice.strip() else
        "\nNo brand voice provided — write ad concepts as adaptable generics.\n"
    )

    prompt = (
        f"You are a senior performance creative strategist.\n"
        f"Analyze {total} competitor ads from: {', '.join(sorted(competitors))}.\n"
        f"{brand_voice_block}\n"
        f"## AD ANALYSES\n\n"
        + "\n\n".join(analyses)
        + f"\n\n{JSON_SCHEMA}"
    )

    response = _get_claude().messages.create(
        model=MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if Claude wrapped it anyway
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _render_html(data: dict, brand_name: str, competitors: set[str],
                 total_ads: int, videos: int, images: int) -> str:
    today = date.today().strftime("%B %d, %Y")
    competitors_str = " · ".join(sorted(competitors))
    json_data = json.dumps(data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Creative Intel — {brand_name or 'Report'}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root{{
    --teal:#0D9488;--teal-light:#CCFBF1;--teal-dark:#0F766E;
    --dark:#1E293B;--mid:#475569;--light:#94A3B8;
    --bg:#F8FAFC;--card:#FFFFFF;--border:#E2E8F0;
    --red:#EF4444;--amber:#F59E0B;--green:#10B981;
    --radius:12px;--shadow:0 2px 12px rgba(0,0,0,.07);
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--dark);line-height:1.6}}
  /* ── Header ── */
  .topbar{{background:var(--dark);color:#fff;padding:16px 40px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.3)}}
  .topbar h1{{font-size:1.1rem;font-weight:700;letter-spacing:.5px}}
  .topbar .meta{{font-size:.8rem;color:var(--light);margin-top:2px}}
  .topbar .print-btn{{background:var(--teal);color:#fff;border:none;padding:8px 20px;border-radius:6px;cursor:pointer;font-size:.85rem;font-weight:600}}
  .topbar .print-btn:hover{{background:var(--teal-dark)}}
  /* ── Layout ── */
  .wrapper{{max-width:1200px;margin:0 auto;padding:32px 24px 80px}}
  /* ── Stats row ── */
  .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:32px}}
  .stat-card{{background:var(--card);border-radius:var(--radius);padding:20px 24px;box-shadow:var(--shadow);border-left:4px solid var(--teal)}}
  .stat-card .val{{font-size:2rem;font-weight:800;color:var(--teal);line-height:1}}
  .stat-card .lbl{{font-size:.78rem;color:var(--mid);margin-top:4px;text-transform:uppercase;letter-spacing:.5px}}
  /* ── Section ── */
  .section{{background:var(--card);border-radius:var(--radius);padding:28px 32px;margin-bottom:24px;box-shadow:var(--shadow)}}
  .section-title{{font-size:1.15rem;font-weight:700;color:var(--teal);border-bottom:2px solid var(--teal-light);padding-bottom:10px;margin-bottom:20px;display:flex;align-items:center;gap:10px}}
  .section-title .num{{background:var(--teal);color:#fff;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.78rem;font-weight:800;flex-shrink:0}}
  /* ── Executive summary ── */
  .exec-card{{background:linear-gradient(135deg,var(--dark) 0%,#334155 100%);color:#fff;border-radius:var(--radius);padding:28px 32px;margin-bottom:24px;position:relative;overflow:hidden}}
  .exec-card::before{{content:'';position:absolute;top:-40px;right:-40px;width:200px;height:200px;background:var(--teal);opacity:.12;border-radius:50%}}
  .meta-pattern{{font-size:1.5rem;font-weight:800;color:var(--teal-light);margin-bottom:12px}}
  .exec-card p{{font-size:.95rem;line-height:1.75;color:#CBD5E1;max-width:760px}}
  /* ── Two-col layout ── */
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px}}
  /* ── Chart containers ── */
  .chart-wrap{{position:relative;height:280px}}
  .chart-label{{font-size:.8rem;color:var(--mid);margin-bottom:12px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}}
  /* ── Hook cards ── */
  .hook-list{{display:flex;flex-direction:column;gap:12px}}
  .hook-item{{border:1px solid var(--border);border-radius:8px;padding:14px 16px}}
  .hook-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}}
  .hook-name{{font-weight:700;font-size:.9rem}}
  .badge{{font-size:.7rem;font-weight:700;padding:2px 8px;border-radius:12px;letter-spacing:.5px}}
  .badge-high{{background:#D1FAE5;color:#065F46}}
  .badge-medium{{background:#FEF3C7;color:#92400E}}
  .badge-low{{background:#FEE2E2;color:#991B1B}}
  .hook-psych{{font-size:.8rem;color:var(--mid);margin-bottom:6px}}
  .hook-examples{{font-size:.78rem;color:var(--light);font-style:italic}}
  /* ── Table ── */
  .intel-table{{width:100%;border-collapse:collapse;font-size:.85rem}}
  .intel-table th{{background:var(--dark);color:#fff;padding:10px 14px;text-align:left;font-size:.78rem;text-transform:uppercase;letter-spacing:.5px}}
  .intel-table td{{padding:10px 14px;border-bottom:1px solid var(--border);vertical-align:top}}
  .intel-table tr:hover td{{background:#F1F5F9}}
  .pct-bar{{height:6px;background:var(--teal);border-radius:3px;margin-top:4px}}
  /* ── Warning cards ── */
  .overused-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}}
  .overused-card{{border:1px solid #FECACA;border-radius:8px;padding:16px;background:#FFF7F7}}
  .overused-name{{font-weight:700;font-size:.9rem;color:var(--red);margin-bottom:6px;display:flex;align-items:center;gap:6px}}
  .overused-name svg{{flex-shrink:0}}
  .sat-bar-bg{{height:6px;background:#FEE2E2;border-radius:3px;margin:8px 0}}
  .sat-bar{{height:6px;background:var(--red);border-radius:3px}}
  .overused-reason{{font-size:.8rem;color:var(--mid)}}
  /* ── Mechanic cards ── */
  .mechanic-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
  .mechanic-card{{border:2px solid var(--teal-light);border-radius:10px;padding:20px;background:linear-gradient(135deg,#F0FDFA,#fff)}}
  .mech-rank{{font-size:2rem;font-weight:900;color:var(--teal-light);line-height:1}}
  .mech-name{{font-weight:700;font-size:1rem;color:var(--teal-dark);margin:6px 0 10px}}
  .mech-label{{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--mid);margin-bottom:4px}}
  .mech-text{{font-size:.82rem;color:var(--dark);margin-bottom:10px}}
  .source-tag{{display:inline-block;font-size:.7rem;background:var(--teal-light);color:var(--teal-dark);padding:2px 8px;border-radius:10px;margin:2px}}
  /* ── Concept cards ── */
  .concept-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
  .concept-card{{border:1px solid var(--border);border-radius:10px;overflow:hidden}}
  .concept-header{{background:var(--dark);color:#fff;padding:12px 16px;display:flex;align-items:center;gap:10px}}
  .concept-num{{background:var(--teal);color:#fff;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.85rem;flex-shrink:0}}
  .concept-name{{font-weight:700;font-size:.95rem}}
  .concept-mechanic{{font-size:.75rem;color:var(--light)}}
  .concept-body{{padding:16px}}
  .field-label{{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--teal);margin-top:10px;margin-bottom:2px}}
  .field-val{{font-size:.83rem;color:var(--dark)}}
  .copy-block{{background:#F8FAFC;border-left:3px solid var(--teal);padding:10px 12px;border-radius:0 6px 6px 0;font-size:.82rem;font-style:italic;color:var(--mid);margin:8px 0}}
  .cta-pill{{display:inline-block;background:var(--teal);color:#fff;padding:4px 14px;border-radius:20px;font-size:.78rem;font-weight:700;margin-top:6px}}
  .why-box{{background:var(--teal-light);border-radius:6px;padding:8px 12px;font-size:.8rem;color:var(--teal-dark);margin-top:8px}}
  /* ── Opportunity badge ── */
  .opp-badge{{display:inline-block;background:#D1FAE5;color:#065F46;font-size:.7rem;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:8px}}
  /* ── Print ── */
  @media print{{
    .topbar .print-btn,.topbar{{position:static}}
    body{{background:#fff}}
    .concept-grid{{grid-template-columns:1fr}}
    .mechanic-grid{{grid-template-columns:1fr}}
  }}
</style>
</head>
<body>
<div class="topbar">
  <div>
    <div class="h1" style="font-size:1.1rem;font-weight:700;color:#fff">
      {'<span style="color:var(--teal-light)">' + brand_name + ' · </span>' if brand_name else ''}
      Competitive Creative Intelligence Report
    </div>
    <div class="meta">{competitors_str} · {total_ads} ads · {today}</div>
  </div>
  <button class="print-btn" onclick="window.print()">⬇ Export / Print</button>
</div>

<div class="wrapper">

  <!-- Stats -->
  <div class="stats">
    <div class="stat-card"><div class="val">{total_ads}</div><div class="lbl">Ads Analyzed</div></div>
    <div class="stat-card"><div class="val">{len(competitors)}</div><div class="lbl">Brands</div></div>
    <div class="stat-card"><div class="val">{videos}</div><div class="lbl">Video Ads</div></div>
    <div class="stat-card"><div class="val">{images}</div><div class="lbl">Image Ads</div></div>
  </div>

  <!-- Executive Summary -->
  <div class="exec-card" id="exec"></div>

  <!-- Hook Structures + Visual Formats -->
  <div class="two-col">
    <div class="section">
      <div class="section-title"><span class="num">2</span> Repeating Hook Structures</div>
      <div style="margin-bottom:16px">
        <div class="chart-label">Frequency by hook type</div>
        <div class="chart-wrap"><canvas id="hookChart"></canvas></div>
      </div>
      <div class="hook-list" id="hookList"></div>
    </div>
    <div class="section">
      <div class="section-title"><span class="num">3</span> Visual Formats</div>
      <div class="chart-wrap"><canvas id="fmtChart"></canvas></div>
      <div id="fmtList" style="margin-top:16px"></div>
    </div>
  </div>

  <!-- Emotional Triggers -->
  <div class="section">
    <div class="section-title"><span class="num">4</span> Recurring Emotional Triggers</div>
    <div class="chart-wrap" style="height:220px"><canvas id="emotionChart"></canvas></div>
    <div id="emotionList" style="margin-top:16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px"></div>
  </div>

  <!-- Copy Frameworks -->
  <div class="section">
    <div class="section-title"><span class="num">5</span> Copy Framework Patterns</div>
    <table class="intel-table" id="fwTable">
      <thead><tr><th>Framework</th><th style="width:80px">Usage</th><th>Structure</th><th>Example</th></tr></thead>
      <tbody id="fwBody"></tbody>
    </table>
  </div>

  <!-- Overused Angles -->
  <div class="section">
    <div class="section-title"><span class="num">6</span> Overused Angles — What to Avoid</div>
    <div class="overused-grid" id="overusedGrid"></div>
  </div>

  <!-- Portable Mechanics -->
  <div class="section">
    <div class="section-title"><span class="num">7</span> Top 3 Portable Mechanics</div>
    <div class="mechanic-grid" id="mechanicGrid"></div>
  </div>

  <!-- Ad Concepts -->
  <div class="section">
    <div class="section-title"><span class="num">8</span> 10 Ready-to-Run Ad Concepts</div>
    <div class="concept-grid" id="conceptGrid"></div>
  </div>

</div>

<script>
const DATA = {json_data};
const TEAL = '#0D9488';
const COLORS = ['#0D9488','#0F766E','#14B8A6','#2DD4BF','#5EEAD4','#99F6E4','#0891B2','#0E7490','#155E75'];
const RED_COLORS = ['#EF4444','#F87171','#FCA5A5','#FECACA'];

// ── Executive Summary ──────────────────────────────────────────────────────
const exec = document.getElementById('exec');
exec.innerHTML = `
  <div class="meta-pattern">"${{DATA.meta_pattern}}"</div>
  <p>${{DATA.executive_summary}}</p>
`;

// ── Hook Chart ─────────────────────────────────────────────────────────────
const hooks = DATA.hook_structures;
new Chart(document.getElementById('hookChart'), {{
  type: 'bar',
  data: {{
    labels: hooks.map(h => h.name),
    datasets: [{{ label: 'Ad count', data: hooks.map(h => h.count),
      backgroundColor: COLORS.slice(0, hooks.length), borderRadius: 4 }}]
  }},
  options: {{
    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ beginAtZero: true, grid: {{ color: '#F1F5F9' }} }},
              y: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 11 }} }} }} }}
  }}
}});

// Hook detail cards
const hl = document.getElementById('hookList');
hooks.forEach(h => {{
  const bc = h.confidence === 'High' ? 'badge-high' : h.confidence === 'Medium' ? 'badge-medium' : 'badge-low';
  hl.innerHTML += `<div class="hook-item">
    <div class="hook-header">
      <span class="hook-name">${{h.name}}</span>
      <span class="badge ${{bc}}">${{h.confidence}}</span>
    </div>
    <div class="hook-psych">${{h.psychology}}</div>
    <div class="hook-examples">${{h.examples.join(' · ')}}</div>
  </div>`;
}});

// ── Format Donut ──────────────────────────────────────────────────────────
const fmts = DATA.visual_formats;
new Chart(document.getElementById('fmtChart'), {{
  type: 'doughnut',
  data: {{
    labels: fmts.map(f => f.name),
    datasets: [{{ data: fmts.map(f => f.percentage),
      backgroundColor: COLORS.slice(0, fmts.length), borderWidth: 2, borderColor: '#fff' }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }} }}
  }}
}});

const fl = document.getElementById('fmtList');
fmts.forEach(f => {{
  fl.innerHTML += `<div style="margin-bottom:8px">
    <div style="display:flex;justify-content:space-between;font-size:.82rem">
      <span style="font-weight:600">${{f.name}}</span>
      <span style="color:var(--mid)">${{f.percentage}}%</span>
    </div>
    <div style="background:#E2E8F0;height:5px;border-radius:3px;margin-top:4px">
      <div style="width:${{f.percentage}}%;background:var(--teal);height:5px;border-radius:3px"></div>
    </div>
    ${{f.note ? `<div style="font-size:.75rem;color:var(--light);margin-top:2px">${{f.note}}</div>` : ''}}
  </div>`;
}});

// ── Emotion Chart ─────────────────────────────────────────────────────────
const emotions = DATA.emotional_triggers;
new Chart(document.getElementById('emotionChart'), {{
  type: 'bar',
  data: {{
    labels: emotions.map(e => e.name),
    datasets: [{{ label: '% of ads', data: emotions.map(e => e.percentage),
      backgroundColor: emotions.map(e => e.is_opportunity ? '#10B981' : TEAL),
      borderRadius: 4 }}]
  }},
  options: {{
    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.raw}}% of ads` }} }} }},
    scales: {{ x: {{ max: 100, beginAtZero: true, grid: {{ color: '#F1F5F9' }},
               ticks: {{ callback: v => v + '%' }} }},
              y: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 11 }} }} }} }}
  }}
}});

const el = document.getElementById('emotionList');
emotions.forEach(e => {{
  el.innerHTML += `<div style="border:1px solid var(--border);border-radius:8px;padding:12px">
    <div style="font-weight:700;font-size:.88rem">
      ${{e.name}}${{e.is_opportunity ? '<span class="opp-badge">OPPORTUNITY</span>' : ''}}
    </div>
    <div style="font-size:.8rem;color:var(--mid);margin-top:4px">${{e.activation}}</div>
  </div>`;
}});

// ── Copy Frameworks ───────────────────────────────────────────────────────
const tb = document.getElementById('fwBody');
DATA.copy_frameworks.forEach(f => {{
  tb.innerHTML += `<tr>
    <td><strong>${{f.name}}</strong></td>
    <td><strong style="color:var(--teal)">${{f.percentage}}%</strong>
      <div class="pct-bar" style="width:${{f.percentage}}%"></div></td>
    <td style="color:var(--mid)">${{f.description}}</td>
    <td style="font-style:italic;color:var(--light);font-size:.8rem">${{f.example}}</td>
  </tr>`;
}});

// ── Overused Angles ───────────────────────────────────────────────────────
const og = document.getElementById('overusedGrid');
DATA.overused_angles.forEach(a => {{
  og.innerHTML += `<div class="overused-card">
    <div class="overused-name">
      <svg width="14" height="14" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
      </svg>
      ${{a.name}}
    </div>
    <div class="sat-bar-bg"><div class="sat-bar" style="width:${{a.saturation_pct}}%"></div></div>
    <div style="font-size:.75rem;color:var(--red);margin-bottom:6px">Saturation: ${{a.saturation_pct}}%</div>
    <div class="overused-reason">${{a.avoid_because}}</div>
  </div>`;
}});

// ── Portable Mechanics ────────────────────────────────────────────────────
const mg = document.getElementById('mechanicGrid');
DATA.portable_mechanics.forEach(m => {{
  const tags = m.source_ads.map(s => `<span class="source-tag">${{s}}</span>`).join('');
  mg.innerHTML += `<div class="mechanic-card">
    <div class="mech-rank">#${{m.rank}}</div>
    <div class="mech-name">${{m.name}}</div>
    <div class="mech-label">How to execute</div>
    <div class="mech-text">${{m.execution}}</div>
    <div class="mech-label">Why it transfers</div>
    <div class="mech-text">${{m.transfer}}</div>
    <div class="mech-label">Source ads</div>
    <div>${{tags}}</div>
  </div>`;
}});

// ── Ad Concepts ───────────────────────────────────────────────────────────
const cg = document.getElementById('conceptGrid');
DATA.ad_concepts.forEach(c => {{
  cg.innerHTML += `<div class="concept-card">
    <div class="concept-header">
      <div class="concept-num">${{c.n}}</div>
      <div><div class="concept-name">${{c.name}}</div>
      <div class="concept-mechanic">↳ ${{c.mechanic}}</div></div>
    </div>
    <div class="concept-body">
      <div class="field-label">Hook — Visual</div><div class="field-val">${{c.hook_visual}}</div>
      <div class="field-label">Hook — Text Overlay</div><div class="field-val" style="font-weight:700">${{c.hook_text}}</div>
      ${{c.hook_spoken ? `<div class="field-label">Hook — Spoken</div><div class="field-val">${{c.hook_spoken}}</div>` : ''}}
      <div class="field-label">Angle</div><div class="field-val">${{c.angle}}</div>
      <div class="field-label">Format</div><div class="field-val">${{c.format}}</div>
      <div class="field-label">Ad Copy</div><div class="copy-block">${{c.copy}}</div>
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:4px">
        <div><div class="field-label">CTA</div><span class="cta-pill">${{c.cta}}</span></div>
        <div style="flex:1"><div class="field-label">Target Avatar</div><div class="field-val" style="font-size:.78rem">${{c.avatar}}</div></div>
      </div>
      <div class="why-box">💡 ${{c.why}}</div>
    </div>
  </div>`;
}});
</script>
</body>
</html>"""


def generate_visual_report(
    ads: list[dict] | None = None,
    base_dir: str = ".",
    brand_name: str = "",
    brand_voice: str = "",
) -> str:
    analyses = _load_analyses(base_dir)
    if not analyses:
        raise ValueError(f"No analysis files in {base_dir}/analyses/")

    if ads:
        competitors, total_ads, videos, images = _extract_meta(ads)
    else:
        competitors = set()
        for a in analyses:
            m = re.match(r"\[([^|]+)\|", a)
            if m:
                competitors.add(m.group(1).strip())
        total_ads = len(analyses)
        videos = images = 0

    print(f"[CLAUDE] Sending {len(analyses)} analyses to {MODEL}...")
    data = _call_claude(analyses, brand_voice, competitors, total_ads)

    html = _render_html(data, brand_name, competitors, total_ads, videos, images)

    out_dir = os.path.join(base_dir, "output")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    dest = os.path.join(out_dir, f"creative-intel_{today}.html")
    Path(dest).write_text(html, encoding="utf-8")
    print(f"[DONE] Report → {dest}")
    return dest
