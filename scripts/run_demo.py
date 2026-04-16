"""
OptiFoot — Mid-Semester Review Demo
Generates all visual outputs for presentation without requiring Raspberry Pi hardware.

Run:  python demo_midsem.py
Outputs saved to:  optifoot/demo_output/

Demo Override:
  After the pipeline runs, you are prompted to press 1 or 0:
    1 → Force output: No Risk, Blood flow 90-99%, SpO₂ ~ 95+
    0 → Force output: Risk Present, Blood flow 1-5%, SpO₂ ~ 3
  Press Enter (blank) to keep the real pipeline result.
"""

import os
import sys
import random
import logging

# Demo mode must be set BEFORE importing pipeline
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from optifoot import config
config.DEMO_MODE = True

import cv2
import numpy as np
from optifoot.pipeline import Pipeline
from optifoot.processing.heatmap import generate_heatmap, overlay_risk_zones, add_colorbar
from optifoot.analysis.temporal import compare_scans, generate_diff_heatmap
from optifoot.analysis.risk_scorer import RiskResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("demo")


# ── Manual Demo Override ───────────────────────────────────────────────────

OVERRIDE_PROFILES = {
    "1": {
        "score": 5.0,
        "label": "Normal",
        "mean_spo2": 97.2,
        "min_spo2": 95.0,
        "pct_critical": 0.0,
        "pct_at_risk": 0.0,
        "pct_monitor": 2.8,
        "pct_normal": 97.2,
        "risk_display": "No Risk",
        "blood_flow": f"{random.uniform(91.0, 98.5):.1f}%",
        "spo2_range": (93.0, 98.0),   # foot pixels will be set to this range
    },
    "0": {
        "score": 82.0,
        "label": "Critical",
        "mean_spo2": 3.0,
        "min_spo2": 1.0,
        "pct_critical": 78.0,
        "pct_at_risk": 15.0,
        "pct_monitor": 5.0,
        "pct_normal": 2.0,
        "risk_display": "Risk Present",
        "blood_flow": f"{random.uniform(1.0, 4.9):.1f}%",
        "spo2_range": (1.0, 5.0),     # foot pixels will be set to this range
    },
}


def ask_demo_choice():
    """Ask the operator for a demo mode at startup. Returns '1', '0', or None."""
    print("\n" + "=" * 50)
    print("  OPTIFOOT DEMO MODE")
    print("  Choose output mode before pipeline starts:")
    print(f"    1  ->  No Risk      (Blood flow {OVERRIDE_PROFILES['1']['blood_flow']})")
    print(f"    0  ->  Risk Present (Blood flow {OVERRIDE_PROFILES['0']['blood_flow']})")
    print("=" * 50)
    key = input("  Enter 1 or 0: ").strip()
    if key in OVERRIDE_PROFILES:
        profile = OVERRIDE_PROFILES[key]
        log.info("Demo mode selected: %s (%s)", profile["risk_display"], profile["blood_flow"])
        return key
    # Default to '1' if invalid input
    log.info("Invalid input '%s', defaulting to mode 1 (No Risk)", key)
    return "1"


def override_spo2_map(spo2_map, profile):
    """Replace all foot-pixel SpO2 values to match the chosen demo profile.

    This ensures the heatmaps visually reflect the demo output.
    """
    modified = spo2_map.copy()
    foot_mask = modified > 0
    lo, hi = profile["spo2_range"]
    # Fill foot pixels with realistic-looking random values in the target range
    modified[foot_mask] = np.random.uniform(lo, hi, size=np.sum(foot_mask)).astype(np.float32)
    return modified


def build_override_result(profile, largest_critical_area_px=0):
    """Build a RiskResult from the demo profile."""
    return RiskResult(
        score=profile["score"],
        label=profile["label"],
        mean_spo2=profile["mean_spo2"],
        min_spo2=profile["min_spo2"],
        pct_critical=profile["pct_critical"],
        pct_at_risk=profile["pct_at_risk"],
        pct_monitor=profile["pct_monitor"],
        pct_normal=profile["pct_normal"],
        largest_critical_area_px=largest_critical_area_px,
        metrics={"demo_override": True,
                 "risk_display": profile["risk_display"],
                 "blood_flow": profile["blood_flow"]},
    )


OUT = os.path.join(os.path.dirname(__file__), "optifoot", "demo_output")
os.makedirs(OUT, exist_ok=True)


def put_title(img, text, y=40, scale=1.0, color=(255, 255, 255)):
    cv2.putText(img, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


def main():
    # ── 0. Ask demo choice FIRST ───────────────────────────────────────
    demo_key = ask_demo_choice()
    profile = OVERRIDE_PROFILES[demo_key]

    pipeline = Pipeline()
    pipeline.start()

    # ── 1. Capture dual-wavelength images ──────────────────────────────
    log.info("Step 1: Dual-wavelength capture (650 nm + 850 nm)")
    img_650, img_850 = pipeline.camera.capture_dual_wavelength()

    # Save raw captures
    cv2.imwrite(os.path.join(OUT, "01_raw_650nm.png"), img_650)
    cv2.imwrite(os.path.join(OUT, "02_raw_850nm.png"), img_850)

    # Side-by-side raw comparison
    h, w = img_650.shape
    side = np.zeros((h + 60, w * 2 + 20, 3), dtype=np.uint8)
    side[60:, :w] = cv2.cvtColor(img_650, cv2.COLOR_GRAY2BGR)
    side[60:, w + 20:] = cv2.cvtColor(img_850, cv2.COLOR_GRAY2BGR)
    put_title(side, "650 nm (Red)", 45, 0.9, (100, 100, 255))
    put_title(side, "850 nm (NIR)", 45, 0.9, (255, 200, 100))
    side[:60, :w] = (40, 40, 60)
    side[:60, w + 20:] = (60, 50, 40)
    # Move text for 850nm label
    cv2.putText(side, "850 nm (NIR)", (w + 40, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 200, 100), 2, cv2.LINE_AA)
    cv2.imwrite(os.path.join(OUT, "03_dual_wavelength_comparison.png"), side)
    log.info("  Saved: dual-wavelength comparison")

    # ── 2. Process -> SpO2 map + heatmap + risk score ──────────────────
    log.info("Step 2: Processing pipeline (preprocess -> SpO2 -> heatmap -> risk)")
    result = pipeline.process(img_650, img_850)

    # ── Apply demo override to SpO2 map + result ───────────────────────
    spo2_map = pipeline.last_spo2_map
    spo2_map = override_spo2_map(spo2_map, profile)
    result = build_override_result(profile, result.largest_critical_area_px)
    log.info("  Override applied: %s (Blood flow %s)", profile["risk_display"], profile["blood_flow"])

    # Save SpO2 heatmap variants (generated from OVERRIDDEN spo2 map)
    heatmap_base = generate_heatmap(spo2_map)
    cv2.imwrite(os.path.join(OUT, "04_spo2_heatmap.png"), heatmap_base)

    heatmap_zones = overlay_risk_zones(heatmap_base.copy(), spo2_map)
    cv2.imwrite(os.path.join(OUT, "05_heatmap_risk_zones.png"), heatmap_zones)

    heatmap_full = add_colorbar(heatmap_zones)
    cv2.imwrite(os.path.join(OUT, "06_heatmap_with_colorbar.png"), heatmap_full)
    log.info("  Saved: heatmaps (plain, risk zones, with colorbar)")

    # ── 3. Risk score summary image ────────────────────────────────────
    log.info("Step 3: Risk score panel")
    panel_h, panel_w = 500, 700
    panel = np.zeros((panel_h, panel_w, 3), dtype=np.uint8)
    panel[:] = (30, 30, 30)

    # Title bar
    cv2.rectangle(panel, (0, 0), (panel_w, 70), (13, 110, 110), -1)
    cv2.putText(panel, "OptiFoot - Risk Assessment Report", (20, 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)

    # Risk score badge
    label_colors = {
        "Normal": (76, 175, 80), "Monitor": (255, 152, 0),
        "At Risk": (255, 87, 34), "Critical": (211, 47, 47),
    }
    badge_color = label_colors.get(result.label, (117, 117, 117))
    cv2.rectangle(panel, (40, 90), (260, 210), badge_color, -1)
    cv2.putText(panel, f"{result.score:.0f}", (80, 175),
                cv2.FONT_HERSHEY_SIMPLEX, 2.5, (255, 255, 255), 4, cv2.LINE_AA)
    cv2.putText(panel, result.label, (75, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, badge_color, 2, cv2.LINE_AA)

    # Metrics
    metrics = [
        (f"Mean SpO2:       {result.mean_spo2:.1f}%", 300, 130),
        (f"Min SpO2:        {result.min_spo2:.1f}%", 300, 165),
        (f"% Critical Area: {result.pct_critical:.1f}%", 300, 200),
        (f"% At Risk Area:  {result.pct_at_risk:.1f}%", 300, 235),
        (f"% Monitor Area:  {result.pct_monitor:.1f}%", 300, 270),
        (f"% Normal Area:   {result.pct_normal:.1f}%", 300, 305),
    ]
    for text, x, y in metrics:
        cv2.putText(panel, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (200, 200, 200), 1, cv2.LINE_AA)

    # Pipeline steps footer
    cv2.line(panel, (20, 340), (panel_w - 20, 340), (60, 60, 60), 1)
    steps = [
        "Pipeline: LED Toggle -> NoIR Capture -> Preprocessing -> Beer-Lambert SpO2 -> Heatmap -> Risk Score",
        "Hardware: Raspberry Pi 4 + NoIR Camera + 650nm/850nm LEDs + Custom PCB",
        f"Algorithm: Dual-wavelength reflectance ratio -> SpO2 via extinction coefficients",
    ]
    for i, s in enumerate(steps):
        cv2.putText(panel, s, (20, 370 + i * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (140, 140, 140), 1, cv2.LINE_AA)

    # Footer
    cv2.rectangle(panel, (0, panel_h - 35), (panel_w, panel_h), (13, 80, 80), -1)
    cv2.putText(panel, "OptiFoot | DS3001 Prototyping & Testing | IIITDM Kancheepuram",
                (20, panel_h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 220, 220), 1, cv2.LINE_AA)

    cv2.imwrite(os.path.join(OUT, "07_risk_score_panel.png"), panel)
    log.info("  Saved: risk score summary panel")

    # ── 4. Simulated temporal comparison (scan 1 vs scan 2) ────────────
    log.info("Step 4: Temporal comparison (simulated two scans)")
    # Second capture with slight variation
    img_650_b, img_850_b = pipeline.camera.capture_dual_wavelength()
    result_b = pipeline.process(img_650_b, img_850_b)
    spo2_map_b = pipeline.last_spo2_map

    comp = compare_scans(spo2_map_b, spo2_map)
    diff_vis = generate_diff_heatmap(comp.diff_map)
    cv2.imwrite(os.path.join(OUT, "08_temporal_diff_map.png"), diff_vis)

    # Build comparison strip
    small_h = 300
    aspect = spo2_map.shape[1] / spo2_map.shape[0]
    small_w = int(small_h * aspect)

    hm1 = cv2.resize(heatmap_full, (small_w, small_h))
    hm2_full = add_colorbar(overlay_risk_zones(generate_heatmap(spo2_map_b), spo2_map_b))
    hm2 = cv2.resize(hm2_full, (small_w, small_h))
    diff_small = cv2.resize(diff_vis, (small_w, small_h))

    strip_h = small_h + 80
    strip = np.zeros((strip_h, small_w * 3 + 40, 3), dtype=np.uint8)
    strip[:] = (25, 25, 25)
    strip[80:, :small_w] = hm1
    strip[80:, small_w + 20: small_w * 2 + 20] = hm2
    strip[80:, small_w * 2 + 40:] = diff_small

    cv2.putText(strip, "Scan 1 (Baseline)", (10, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (100, 200, 200), 2, cv2.LINE_AA)
    cv2.putText(strip, "Scan 2 (Follow-up)", (small_w + 30, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (100, 200, 200), 2, cv2.LINE_AA)
    cv2.putText(strip, "Difference Map", (small_w * 2 + 50, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 160, 100), 2, cv2.LINE_AA)

    cv2.imwrite(os.path.join(OUT, "09_temporal_comparison_strip.png"), strip)
    log.info("  Saved: temporal comparison strip")

    # ── 5. Architecture diagram (text-based) ───────────────────────────
    log.info("Step 5: Software architecture diagram")
    arch_h, arch_w = 400, 900
    arch = np.zeros((arch_h, arch_w, 3), dtype=np.uint8)
    arch[:] = (20, 20, 30)

    # Title
    cv2.putText(arch, "OptiFoot - Software Architecture", (180, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 212, 170), 2, cv2.LINE_AA)

    # Pipeline boxes
    boxes = [
        ("GPIO LED\nControl", 20, 70, 140, 60, (13, 110, 110)),
        ("PiCamera2\nCapture", 180, 70, 140, 60, (13, 110, 110)),
        ("Preprocess\n(Blur+Align+Mask)", 340, 70, 165, 60, (46, 125, 50)),
        ("Beer-Lambert\nSpO2 Map", 525, 70, 150, 60, (150, 100, 20)),
        ("Heatmap +\nRisk Zones", 695, 70, 150, 60, (150, 60, 30)),
        ("Threshold\nRisk Scorer", 340, 180, 165, 60, (180, 80, 20)),
        ("PyQt5\nDesktop GUI", 525, 180, 150, 60, (80, 80, 150)),
        ("SQLite\nScan History", 695, 180, 150, 60, (60, 80, 120)),
        ("Temporal\nAnalysis", 340, 290, 165, 60, (100, 50, 100)),
        ("Future: ML\nClassifier", 525, 290, 150, 55, (80, 80, 80)),
    ]
    for label, x, y, w_box, h_box, color in boxes:
        cv2.rectangle(arch, (x, y), (x + w_box, y + h_box), color, -1)
        cv2.rectangle(arch, (x, y), (x + w_box, y + h_box), (200, 200, 200), 1)
        lines = label.split("\n")
        for i, line in enumerate(lines):
            ty = y + 22 + i * 22
            cv2.putText(arch, line, (x + 8, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                        (255, 255, 255), 1, cv2.LINE_AA)

    # Arrows (horizontal pipeline)
    for x_start in [160, 320, 505, 675]:
        cv2.arrowedLine(arch, (x_start, 100), (x_start + 20, 100), (0, 212, 170), 2, tipLength=0.4)

    # Vertical arrows
    cv2.arrowedLine(arch, (440, 130), (440, 180), (0, 212, 170), 2, tipLength=0.3)
    cv2.arrowedLine(arch, (600, 130), (600, 180), (0, 212, 170), 2, tipLength=0.3)
    cv2.arrowedLine(arch, (770, 130), (770, 180), (0, 212, 170), 2, tipLength=0.3)
    cv2.arrowedLine(arch, (440, 240), (440, 290), (150, 150, 150), 2, tipLength=0.3)
    cv2.arrowedLine(arch, (600, 240), (600, 290), (150, 150, 150), 2, tipLength=0.3)

    # Legend
    cv2.putText(arch, "Solid = Implemented    Gray = Future Phase", (250, 380),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 120), 1, cv2.LINE_AA)

    cv2.imwrite(os.path.join(OUT, "10_architecture_diagram.png"), arch)
    log.info("  Saved: architecture diagram")

    # ── 6. Database persistence demo ───────────────────────────────────
    log.info("Step 6: Database persistence")
    scan_id = pipeline.save_scan("DEMO_PATIENT")
    scans = pipeline.db.list_scans("DEMO_PATIENT")
    log.info("  Saved %d scan(s) to SQLite for patient DEMO_PATIENT", len(scans))

    pipeline.shutdown()

    # ── Summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  OptiFoot Mid-Sem Demo — All outputs generated!")
    print("=" * 60)
    print(f"\n  Output folder: {OUT}\n")
    for f in sorted(os.listdir(OUT)):
        if f.endswith(".png"):
            size = os.path.getsize(os.path.join(OUT, f)) / 1024
            print(f"    {f:45s} ({size:.0f} KB)")

    # Show override-aware summary
    risk_display = result.metrics.get("risk_display", result.label)
    blood_flow = result.metrics.get("blood_flow", f"{result.mean_spo2:.1f}%")
    is_overridden = result.metrics.get("demo_override", False)

    print(f"\n  Risk:        {risk_display}")
    print(f"  Blood Flow:  {blood_flow}")
    print(f"  Risk Score:  {result.score:.0f}/100  [{result.label}]")
    print(f"  Mean SpO2:   {result.mean_spo2:.1f}%")
    if is_overridden:
        print(f"  *** DEMO OVERRIDE ACTIVE ***")
    print(f"  Pipeline:    LED -> Capture -> Preprocess -> SpO2 -> Heatmap -> Score")
    print(f"\n  To launch GUI:  python -m optifoot.main --demo")
    print("=" * 60)


if __name__ == "__main__":
    main()
