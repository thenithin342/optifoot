"""Build a self-contained HTML report (embedded images) for one dual-wavelength scan."""
from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Any


def _img_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def write_scan_report(
    output_html: Path,
    *,
    analysis: dict[str, Any],
    image_paths: dict[str, Path],
) -> None:
    """Write one HTML file with embedded PNGs. `image_paths` keys: raw650, raw850, analysis_heatmap, zones, comparison."""
    output_html.parent.mkdir(parents=True, exist_ok=True)

    def uri(key: str) -> str:
        p = image_paths.get(key)
        if not p or not p.is_file():
            return ""
        return _img_data_uri(p)

    r = analysis.get("risk", {})
    sp = analysis.get("spo2", {})
    nar = analysis.get("narrative", {})
    lines = nar.get("lines", [])
    lines_html = "".join(f"<p>{html.escape(t)}</p>" for t in lines)

    files = analysis.get("files") or {}
    f650n = html.escape(str(files.get("650", "")))
    f850n = html.escape(str(files.get("850", "")))

    title = f"OptiFoot scan — {html.escape(analysis.get('pair_id', 'unknown'))}"
    risk_label = html.escape(str(r.get("label", "")))
    risk_color = "#c0392b" if r.get("label") in ("Critical", "At Risk") else "#27ae60"
    if r.get("label") == "Monitor":
        risk_color = "#f39c12"

    body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
<style>
:root {{ font-family: "Segoe UI", system-ui, sans-serif; background: #0f1419; color: #e8eaed; }}
body {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }}
header {{ border-bottom: 1px solid #30363d; padding-bottom: 16px; margin-bottom: 24px; }}
h1 {{ font-size: 1.35rem; font-weight: 600; margin: 0 0 8px; }}
.sub {{ color: #8b949e; font-size: 0.95rem; }}
.badge {{ display: inline-block; padding: 6px 14px; border-radius: 8px; font-weight: 700;
  background: {risk_color}; color: #fff; margin-top: 12px; }}
.grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 20px 0; }}
@media (max-width: 800px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 14px; }}
.card h3 {{ margin: 0 0 10px; font-size: 1rem; color: #58a6ff; }}
.card img {{ width: 100%; height: auto; border-radius: 8px; display: block; }}
.full {{ margin: 20px 0; }}
.full img {{ width: 100%; height: auto; border-radius: 12px; border: 1px solid #30363d; }}
table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.95rem; }}
th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #30363d; }}
th {{ color: #8b949e; font-weight: 500; width: 42%; }}
.narrative {{ background: #161b22; border-radius: 12px; padding: 16px 20px; margin: 24px 0;
  border-left: 4px solid #58a6ff; }}
.narrative p {{ margin: 8px 0; line-height: 1.5; }}
footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #30363d; color: #6e7681; font-size: 0.85rem; }}
</style></head><body>
<header>
  <h1>OptiFoot — tissue oxygenation report</h1>
  <p class="sub">Pair: {html.escape(analysis.get("pair_id", ""))} · Raw files: {f650n} &amp; {f850n}</p>
  <span class="badge">Risk: {risk_label} (Score: {float(r.get("score", 0)):.1f}/100 | Avg SpO₂: {float(sp.get("mean", 0)):.1f}%)</span>
</header>

<section class="grid2">
  <div class="card"><h3>650 nm (red)</h3><img src="{uri("raw650")}" alt="650 nm"/></div>
  <div class="card"><h3>850 nm (NIR)</h3><img src="{uri("raw850")}" alt="850 nm"/></div>
</section>

<section class="full"><h3 style="margin-bottom:10px">SpO₂ map with risk zones</h3>
<img src="{uri("analysis_heatmap")}" alt="Analysis heatmap"/></section>

<section class="grid2">
  <div class="card"><h3>Risk-zone heatmap</h3><img src="{uri("zones")}" alt="Zones"/></div>
  <div class="card"><h3>650 · 850 · SpO₂ strip</h3><img src="{uri("comparison")}" alt="Comparison"/></div>
</section>

<h3 style="margin-top:28px">Measurements</h3>
<table>
<tr><th>650 nm mean (raw)</th><td>{float(analysis.get("mean_650", 0)):.1f}</td></tr>
<tr><th>850 nm mean (raw)</th><td>{float(analysis.get("mean_850", 0)):.1f}</td></tr>
<tr><th>Foot region</th><td>{float(analysis.get("foot_pct", 0)):.1f}% of frame</td></tr>
<tr><th>SpO₂ mean (foot)</th><td>{float(sp.get("mean", 0)):.1f}%</td></tr>
<tr><th>SpO₂ min (foot)</th><td>{float(sp.get("min", 0)):.1f}%</td></tr>
<tr><th>SpO₂ max (foot)</th><td>{float(sp.get("max", 0)):.1f}%</td></tr>
<tr><th>SpO₂ std dev</th><td>{float(sp.get("std", 0)):.1f}%</td></tr>
<tr><th>% area critical (&lt;85%)</th><td>{float(r.get("pct_critical", 0)):.1f}%</td></tr>
<tr><th>% area at risk (85–90%)</th><td>{float(r.get("pct_at_risk", 0)):.1f}%</td></tr>
<tr><th>% area monitor (90–95%)</th><td>{float(r.get("pct_monitor", 0)):.1f}%</td></tr>
<tr><th>% area normal (≥95%)</th><td>{float(r.get("pct_normal", 0)):.1f}%</td></tr>
<tr><th>Largest critical cluster</th><td>{int(r.get("largest_critical_area_px", 0)):,} px</td></tr>
</table>

<div class="narrative"><h3 style="margin-top:0">Clinical-style summary</h3>{lines_html}</div>

<footer>
  Research / demonstration output only — not a medical device. Do not use for diagnosis or treatment decisions.
</footer>
</body></html>"""

    output_html.write_text(body, encoding="utf-8")
