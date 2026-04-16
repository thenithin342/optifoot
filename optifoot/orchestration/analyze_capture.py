import sys
from pathlib import Path
from typing import Any
from optifoot.paths import CAPTURES_DIR, REPO_ROOT, find_latest_capture_pair
sys.path.insert(0, str(REPO_ROOT))

import cv2
import numpy as np

from optifoot.processing.preprocessing import preprocess, align_images, create_foot_mask
from optifoot.processing.oxygenation import calculate_spo2_map
from optifoot.processing.heatmap import generate_heatmap, overlay_risk_zones, add_colorbar
from optifoot.analysis.risk_scorer import ThresholdScorer


def analyze_pair(
    pair: tuple[Path, Path],
    *,
    out_dir: Path | None = None,
    print_report: bool = True,
    mock_mode: int | None = None,
) -> dict[str, Any]:
    """
    Run preprocessing → SpO₂ map → risk score → save analysis_heatmap.png under out_dir.
    Returns a dict suitable for HTML reporting.
    """
    out = out_dir or CAPTURES_DIR
    out.mkdir(parents=True, exist_ok=True)
    p650, p850 = pair
    pair_id = p650.name.replace("_650nm.png", "")

    img_650 = cv2.imread(str(p650), cv2.IMREAD_GRAYSCALE)
    img_850 = cv2.imread(str(p850), cv2.IMREAD_GRAYSCALE)
    if img_650 is None or img_850 is None:
        raise FileNotFoundError(f"Failed to read images: {p650}, {p850}")

    p650p = preprocess(img_650)
    p850p = preprocess(img_850)
    p650p, p850p = align_images(p650p, p850p)
    mask = create_foot_mask(p650p)
    foot_pixels = int(np.sum(mask > 0))
    total_pixels = mask.shape[0] * mask.shape[1]
    foot_pct = foot_pixels / total_pixels * 100.0

    spo2_map = calculate_spo2_map(p650p, p850p, mask)
    
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

    ulcer_suspected = result.label in ("Critical", "At Risk")
    narrative_lines: list[str] = []
    narrative_lines.append(
        f"Ulcer concern (rule-based): {'YES' if ulcer_suspected else 'NO'}."
    )
    if ulcer_suspected:
        narrative_lines.append(
            f"Risk score {result.score:.1f}/100 with label “{result.label}”. "
            f"{result.pct_critical:.1f}% of the foot mask is below 85% SpO₂ (critical band)."
        )
        narrative_lines.append(
            "Suggested action: clinical review of the foot and vascular status (research context only)."
        )
    else:
        narrative_lines.append(
            f"Risk score {result.score:.1f}/100 with label “{result.label}”. "
            "Tissue oxygenation appears relatively preserved in this model output."
        )
        if result.label == "Monitor":
            narrative_lines.append(
                f"{result.pct_monitor:.1f}% of the area is in the 90–95% monitor band — consider follow-up imaging."
            )
        else:
            narrative_lines.append("No critical oxygenation pattern flagged by the threshold scorer.")

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
        "foot_pct": foot_pct,
        "spo2": spo2_stats,
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
