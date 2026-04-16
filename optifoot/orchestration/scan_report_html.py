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

    # Error handling
    if "error" in analysis:
        error_msg = html.escape(analysis["error"])
        body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>OptiFoot — Analysis Error</title>
<style>
body {{ font-family: "Segoe UI", system-ui, sans-serif; background: #0f1419; color: #e8eaed; padding: 40px; }}
.error {{ background: #4a1c1c; border: 2px solid #c0392b; border-radius: 12px; padding: 24px; max-width: 600px; margin: 0 auto; }}
h1 {{ color: #e74c3c; }}
</style></head><body>
<div class="error"><h1>Analysis Failed</h1><p>{error_msg}</p></div>
</body></html>"""
        output_html.write_text(body, encoding="utf-8")
        return

    # Quality metrics
    q = analysis.get("quality", {})
    align_pass = q.get("alignment_pass", False)
    align_score = q.get("alignment_score", 0)
    snr_650 = q.get("snr_650", 0)
    snr_850 = q.get("snr_850", 0)
    foot_pct = analysis.get("foot_pct", 0)

    # R-ratio
    rr = analysis.get("r_ratio", {})
    r_mean = rr.get("mean", 0)
    r_std = rr.get("std", 0)

    # v1 vs v2 comparison
    cmp = analysis.get("spo2_comparison", {})

    title = f"OptiFoot scan — {html.escape(analysis.get('pair_id', 'unknown'))}"
    risk_label = html.escape(str(r.get("label", "")))
    risk_color = "#c0392b" if r.get("label") in ("Critical", "At Risk") else "#27ae60"
    if r.get("label") == "Monitor":
        risk_color = "#f39c12"

    # Quality warning banner
    quality_warnings = []
    if not align_pass:
        quality_warnings.append(f"Low alignment score ({align_score:.3f}) — motion artifact possible")
    if snr_650 < 3:
        quality_warnings.append(f"Low SNR 650nm ({snr_650:.1f}) — check illumination")
    if snr_850 < 3:
        quality_warnings.append(f"Low SNR 850nm ({snr_850:.1f}) — check illumination")
    if foot_pct < 10:
        quality_warnings.append(f"Low foot coverage ({foot_pct:.1f}%) — reposition foot")

    quality_banner = ""
    if quality_warnings:
        warnings_html = "".join(f"<li>{html.escape(w)}</li>" for w in quality_warnings)
        quality_banner = f"""
<div style="background:#4a2a0a;border-left:4px solid #f39c12;padding:16px;margin:20px 0;border-radius:8px;">
  <strong style="color:#f39c12;">Quality Warnings:</strong>
  <ul style="margin:8px 0 0 20px;color:#f5c58b;">{warnings_html}</ul>
</div>"""

    body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
<style>
:root {{ font-family: "Segoe UI", system-ui, sans-serif; background: #0f1419; color: #e8eaed; }}
body {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }}
header {{ border-bottom: 1px solid #30363d; padding-bottom: 16px; margin-bottom: 24px; }}
h1, h2, h3 {{ margin-top: 0; }}
.sub {{ color: #8b949e; font-size: 0.95rem; }}
.badge {{ display: inline-block; padding: 8px 16px; border-radius: 8px; font-weight: 700;
  background: {risk_color}; color: #fff; margin-top: 12px; font-size: 1.1rem; }}
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
.narrative p {{ margin: 8px 0; line-height: 1.5; white-space: pre-wrap; }}
.quality-card {{ background: #1a1f2e; border: 1px solid #30363d; border-radius: 12px; padding: 14px; margin-bottom: 16px; }}
.quality-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
.q-item {{ background: #0f1419; padding: 10px; border-radius: 8px; text-align: center; }}
.q-label {{ color: #8b949e; font-size: 0.85rem; }}
.q-value {{ font-size: 1.2rem; font-weight: 600; color: #e8eaed; margin-top: 4px; }}
.q-pass {{ color: #27ae60; }}
.q-fail {{ color: #c0392b; }}
.comparison-table {{ margin: 16px 0; }}
.comparison-table th {{ background: #1f2937; }}
.delta-pos {{ color: #27ae60; }}
.delta-neg {{ color: #c0392b; }}
footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #30363d; color: #6e7681; font-size: 0.85rem; }}
</style></head><body>

<header>
  <h1>OptiFoot — Tissue Oxygenation Report</h1>
  <p class="sub">Pair: {html.escape(analysis.get("pair_id", ""))} · Files: {f650n} &amp; {f850n}</p>
  <span class="badge">Risk: {risk_label} (Score: {float(r.get("score", 0)):.1f}/100)</span>
</header>

{quality_banner}

<section class="quality-card">
  <h3>Quality Indicators</h3>
  <div class="quality-grid">
    <div class="q-item">
      <div class="q-label">Alignment Score</div>
      <div class="q-value {'q-pass' if align_pass else 'q-fail'}">{align_score:.3f} {'✓' if align_pass else '✗'}</div>
    </div>
    <div class="q-item">
      <div class="q-label">Foot Coverage</div>
      <div class="q-value {'q-pass' if foot_pct >= 10 else 'q-fail'}">{foot_pct:.1f}%</div>
    </div>
    <div class="q-item">
      <div class="q-label">SNR (650/850 nm)</div>
      <div class="q-value">{snr_650:.1f} / {snr_850:.1f}</div>
    </div>
    <div class="q-item">
      <div class="q-label">R-Ratio Mean</div>
      <div class="q-value">{r_mean:.3f} ±{r_std:.2f}</div>
    </div>
    <div class="q-item">
      <div class="q-label">Valid SpO₂ Pixels</div>
      <div class="q-value">{q.get('spo2_valid_pixels', 0):,}</div>
    </div>
    <div class="q-item">
      <div class="q-label">Formula Used</div>
      <div class="q-value">Beer-Lambert v2</div>
    </div>
  </div>
</section>

<section class="grid2">
  <div class="card"><h3>650 nm (Red)</h3><img src="{uri("raw650")}" alt="650 nm"/></div>
  <div class="card"><h3>850 nm (NIR)</h3><img src="{uri("raw850")}" alt="850 nm"/></div>
</section>

<section class="full"><h3 style="margin-bottom:10px">SpO₂ Map (Risk Zones)</h3>
<img src="{uri("analysis_heatmap")}" alt="Analysis heatmap"/></section>

<section class="grid2">
  <div class="card"><h3>Risk-Zone Heatmap</h3><img src="{uri("zones")}" alt="Zones"/></div>
  <div class="card"><h3>Comparison Strip</h3><img src="{uri("comparison")}" alt="Comparison"/></div>
</section>

<h2 style="margin-top:32px">Measurements</h2>
<table>
<tr><th>650 nm mean (raw)</th><td>{float(analysis.get("mean_650", 0)):.1f}</td></tr>
<tr><th>850 nm mean (raw)</th><td>{float(analysis.get("mean_850", 0)):.1f}</td></tr>
<tr><th>Foot coverage</th><td>{float(analysis.get("foot_pct", 0)):.1f}% of frame</td></tr>
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

<h2 style="margin-top:32px">Formula Comparison (v1 vs v2)</h2>
<p style="color:#8b949e;margin-bottom:12px;">Side-by-side comparison of Beer-Lambert implementations. V2 uses corrected denominator sign convention.</p>
<table class="comparison-table">
<tr><th>Metric</th><th>V1 (Original)</th><th>V2 (Corrected)</th><th>Delta</th></tr>
<tr><td>Mean SpO₂</td><td>{cmp.get('v1_mean', 0):.1f}%</td><td>{cmp.get('v2_mean', 0):.1f}%</td><td class="{'delta-pos' if cmp.get('delta', 0) >= 0 else 'delta-neg'}">{cmp.get('delta', 0):+.1f}%</td></tr>
<tr><td>Min SpO₂</td><td>{cmp.get('v1_min', 0):.1f}%</td><td>{cmp.get('v2_min', 0):.1f}%</td><td>—</td></tr>
</table>

<h2 style="margin-top:32px">Physiology Context</h2>
<div class="card" style="border-left:4px solid #58a6ff;">
  <p style="margin:0;"><strong>Normal tissue SpO₂:</strong> 60-80% (healthy perfusion)</p>
  <p style="margin:8px 0 0 0;"><strong>Critical ischemia:</strong> &lt;50% (urgent clinical attention)</p>
  <p style="margin:8px 0 0 0; color:#8b949e; font-size:0.9rem;">Note: This device uses dual-wavelength reflectance oximetry. Values are research-grade and not calibrated for clinical diagnosis.</p>
</div>

<div class="narrative"><h3 style="margin-top:0">Clinical Interpretation</h3>{lines_html}</div>

<footer>
  <strong>Research / demonstration output only — not a medical device.</strong><br/>
  Do not use for diagnosis or treatment decisions. OptiFoot is a prototype for educational and research purposes.
</footer>
</body></html>"""

    output_html.write_text(body, encoding="utf-8")
