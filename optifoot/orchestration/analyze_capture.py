import sys
from pathlib import Path
from typing import Any
from optifoot.paths import CAPTURES_DIR, REPO_ROOT, find_latest_capture_pair
sys.path.insert(0, str(REPO_ROOT))

import cv2
import numpy as np

from optifoot.processing.preprocessing import preprocess, align_images, create_foot_mask
from optifoot.processing.oxygenation import calculate_spo2_map, calculate_spo2_map_v2, calculate_r_ratio
from optifoot.processing.heatmap import generate_heatmap, overlay_risk_zones, add_colorbar
from optifoot.analysis.risk_scorer import ThresholdScorer


def _validate_input_pair(p650: Path, p850: Path) -> tuple[np.ndarray, np.ndarray] | dict[str, Any]:
    """Validate input images. Returns (img_650, img_850) on success, error dict on failure."""
    if not p650.is_file():
        return {"error": f"Missing 650nm image: {p650}"}
    if not p850.is_file():
        return {"error": f"Missing 850nm image: {p850}"}

    img_650 = cv2.imread(str(p650), cv2.IMREAD_GRAYSCALE)
    img_850 = cv2.imread(str(p850), cv2.IMREAD_GRAYSCALE)

    if img_650 is None or img_850 is None:
        return {"error": f"Failed to read images (corrupted or unsupported format)"}

    if img_650.shape != img_850.shape:
        return {"error": f"Image dimensions mismatch: 650nm={img_650.shape}, 850nm={img_850.shape}"}

    if img_650.mean() < 5 or img_850.mean() < 5:
        return {"error": "Images appear all-black (possible capture failure)"}

    return (img_650, img_850)


def analyze_pair(
    pair: tuple[Path, Path],
    *,
    out_dir: Path | None = None,
    print_report: bool = True,
    mock_mode: int | None = None,
) -> dict[str, Any]:
    """
    Run preprocessing → SpO₂ map (v1 + v2) → risk score → save analysis_heatmap.png under out_dir.
    Returns a dict suitable for HTML reporting.
    """
    out = out_dir or CAPTURES_DIR
    out.mkdir(parents=True, exist_ok=True)
    p650, p850 = pair
    pair_id = p650.name.replace("_650nm.png", "")

    # Validate inputs
    validation = _validate_input_pair(p650, p850)
    if isinstance(validation, dict) and "error" in validation:
        return {
            "pair_id": pair_id,
            "error": validation["error"],
            "files": {"650": p650.name, "850": p850.name},
        }
    img_650, img_850 = validation

    p650p = preprocess(img_650)
    p850p = preprocess(img_850)
    p650p, p850p_aligned = align_images(p650p, p850p)
    mask = create_foot_mask(p650p)
    foot_pixels = int(np.sum(mask > 0))
    total_pixels = mask.shape[0] * mask.shape[1]
    foot_pct = foot_pixels / total_pixels * 100.0

    # Compute alignment quality (ECC correlation)
    try:
        warp_matrix = np.eye(2, 3, dtype=np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4)
        _, warp_matrix = cv2.findTransformECC(
            p650p.astype(np.float32),
            p850p.astype(np.float32),
            warp_matrix,
            cv2.MOTION_EUCLIDEAN,
            criteria,
        )
        alignment_score = float(_)  # correlation coefficient
    except cv2.error:
        alignment_score = 0.0

    # SNR estimate (signal mean / std in foot region)
    snr_650 = float(p650p[mask > 0].mean() / (p650p[mask > 0].std() + 1e-6)) if foot_pixels > 0 else 0.0
    snr_850 = float(p850p[mask > 0].mean() / (p850p[mask > 0].std() + 1e-6)) if foot_pixels > 0 else 0.0

    # Compute SpO2 maps (v1 and v2)
    spo2_map_v1 = calculate_spo2_map(p650p, p850p_aligned, mask)
    spo2_map_v2 = calculate_spo2_map_v2(p650p, p850p_aligned, mask)

    # Compute R-ratio map
    r_map = calculate_r_ratio(p650p, p850p_aligned, mask)
    r_mean = float(r_map[mask > 0].mean()) if foot_pixels > 0 else 0.0
    r_std = float(r_map[mask > 0].std()) if foot_pixels > 0 else 0.0

    # Use v2 for primary analysis (mock mode applies to v2)
    spo2_map = spo2_map_v2.copy()

    if mock_mode in (0, 1):
        pair_num = int("".join(filter(str.isdigit, pair_id)) or "42")
        rng = np.random.default_rng(pair_num)
        foot_mask = (mask > 0)
        n_pixels = np.count_nonzero(foot_mask)
        if mock_mode == 1:
            spo2_map[foot_mask] = rng.uniform(86.0, 96.0, size=n_pixels)
        elif mock_mode == 0:
            spo2_map[foot_mask] = rng.uniform(2.0, 8.0, size=n_pixels)

    foot_vals = spo2_map[spo2_map > 0]
    spo2_stats: dict[str, float] = {}
    if foot_vals.size > 0:
        spo2_stats = {
            "mean": float(foot_vals.mean()),
            "min": float(foot_vals.min()),
            "max": float(foot_vals.max()),
            "std": float(foot_vals.std()),
        }

    # Compute v1 vs v2 comparison stats
    v1_foot_vals = spo2_map_v1[spo2_map_v1 > 0]
    v2_foot_vals = spo2_map[spo2_map > 0]
    spo2_comparison = {}
    if v1_foot_vals.size > 0 and v2_foot_vals.size > 0:
        spo2_comparison = {
            "v1_mean": float(v1_foot_vals.mean()),
            "v2_mean": float(v2_foot_vals.mean()),
            "delta": float(v2_foot_vals.mean() - v1_foot_vals.mean()),
            "v1_min": float(v1_foot_vals.min()),
            "v2_min": float(v2_foot_vals.min()),
        }

    scorer = ThresholdScorer()
    result = scorer.score(spo2_map)

    if mock_mode == 1:
        result.label = "Normal"
        result.score = 5.0
        result.pct_critical = 0.0
        result.pct_at_risk = 0.0
        result.pct_monitor = 0.0
        result.pct_normal = 100.0
    elif mock_mode == 0:
        result.label = "Critical"
        result.score = 100.0
        result.pct_critical = 100.0
        result.pct_at_risk = 0.0
        result.pct_monitor = 0.0
        result.pct_normal = 0.0

    risk = {
        "score": float(result.score),
        "label": result.label,
        "mean_spo2": float(result.mean_spo2),
        "min_spo2": float(result.min_spo2),
        "pct_critical": float(result.pct_critical),
        "pct_at_risk": float(result.pct_at_risk),
        "pct_monitor": float(result.pct_monitor),
        "pct_normal": float(result.pct_normal),
        "largest_critical_area_px": int(result.largest_critical_area_px),
    }

    # Clinical narrative with physiology context
    ulcer_suspected = result.label in ("Critical", "At Risk")
    narrative_lines: list[str] = []

    # Risk classification with action
    if ulcer_suspected:
        narrative_lines.append(
            f"**ULCER RISK DETECTED** "" Risk score {result.score:.1f}/100 ({result.label})."
        )
        narrative_lines.append(
            f"{result.pct_critical:.1f}% of tissue area has SpO₂ <85% (critical ischemia threshold)."
        )
        if result.pct_critical > 50:
            narrative_lines.append(
                "**Action recommended**: Urgent clinical review for vascular assessment. "
                "Extended pressure offloading and perfusion evaluation advised."
            )
        else:
            narrative_lines.append(
                "**Action recommended**: Clinical follow-up within 48-72 hours. "
                "Consider pressure redistribution and repeat imaging."
            )
    else:
        narrative_lines.append(
            f"**NO ULCER RISK** "" Risk score {result.score:.1f}/100 ({result.label})."
        )
        narrative_lines.append(
            "Tissue oxygenation within acceptable range for this measurement modality."
        )
        if result.label == "Monitor":
            narrative_lines.append(
                f"{result.pct_monitor:.1f}% of area in 90-95% monitor band "" routine follow-up recommended."
            )
        else:
            narrative_lines.append("Continue routine monitoring per clinical protocol.")

    # Physiology context
    narrative_lines.append("")
    narrative_lines.append(
        "**Physiology context**: Normal tissue SpO₂: 60-80% | Critical ischemia: <50% | "
        "This device uses dual-wavelength reflectance oximetry (research prototype)."
    )

    heatmap = generate_heatmap(spo2_map)
    heatmap_zones = overlay_risk_zones(heatmap.copy(), spo2_map)
    heatmap_final = add_colorbar(heatmap_zones)
    heatmap_path = out / "analysis_heatmap.png"
    cv2.imwrite(str(heatmap_path), heatmap_final)

    data: dict[str, Any] = {
        "pair_id": pair_id,
        "files": {"650": p650.name, "850": p850.name},
        "shape_650": tuple(int(x) for x in img_650.shape),
        "shape_850": tuple(int(x) for x in img_850.shape),
        "mean_650": float(img_650.mean()),
        "mean_850": float(img_850.mean()),
        "min_650": int(img_650.min()),
        "max_650": int(img_650.max()),
        "min_850": int(img_850.min()),
        "max_850": int(img_850.max()),
        "mean_650_pre": float(p650p.mean()),
        "mean_850_pre": float(p850p.mean()),
        "foot_pixels": foot_pixels,
        "foot_pct": round(foot_pct, 1),
        "quality": {
            "alignment_score": round(alignment_score, 4),
            "alignment_pass": alignment_score > 0.7,
            "snr_650": round(snr_650, 1),
            "snr_850": round(snr_850, 1),
            "spo2_valid_pixels": int(foot_pixels),
        },
        "r_ratio": {
            "mean": round(r_mean, 3),
            "std": round(r_std, 3),
        },
        "spo2": spo2_stats,
        "spo2_comparison": spo2_comparison,
        "risk": risk,
        "narrative": {"ulcer_suspected": ulcer_suspected, "lines": narrative_lines},
        "paths": {"analysis_heatmap": heatmap_path},
    }

    if print_report:
        print(f"Using pair: {p650.name} + {p850.name}")
        print(f"650nm shape: {img_650.shape}, mean: {img_650.mean():.1f}")
        print(f"850nm shape: {img_850.shape}, mean: {img_850.mean():.1f}")
        if spo2_stats:
            print(f"SpO2 foot mean: {spo2_stats['mean']:.1f}%")
        print(f"Risk: {result.label} ({result.score:.1f}/100)")
        print(f"Heatmap saved: {heatmap_path}")

    return data


def main(pair: tuple[Path, Path] | None = None) -> None:
    p650, p850 = pair if pair is not None else find_latest_capture_pair()
    analyze_pair((p650, p850), print_report=True)


if __name__ == "__main__":
    main()
