import sys
from pathlib import Path

from project_paths import CAPTURES_DIR, REPO_ROOT, find_latest_capture_pair

sys.path.insert(0, str(REPO_ROOT))

import cv2
import numpy as np

from optifoot.processing.preprocessing import preprocess, align_images, create_foot_mask
from optifoot.processing.oxygenation import calculate_spo2_map
from optifoot.processing.heatmap import generate_heatmap, overlay_risk_zones, add_colorbar


def run_heatmaps(
    pair: tuple[Path, Path],
    *,
    out_dir: Path | None = None,
    print_report: bool = True,
) -> dict[str, Path]:
    """Write spo2_heatmap_pure, spo2_heatmap_zones, comparison_strip under out_dir."""
    out = out_dir or CAPTURES_DIR
    out.mkdir(parents=True, exist_ok=True)
    p650, p850 = pair

    img_650 = cv2.imread(str(p650), cv2.IMREAD_GRAYSCALE)
    img_850 = cv2.imread(str(p850), cv2.IMREAD_GRAYSCALE)
    if img_650 is None or img_850 is None:
        raise FileNotFoundError(f"Failed to read images: {p650}, {p850}")

    p650p = preprocess(img_650)
    p850p = preprocess(img_850)
    p650p, p850p = align_images(p650p, p850p)
    mask = create_foot_mask(p650p)
    spo2_map = calculate_spo2_map(p650p, p850p, mask)

    heatmap_pure = generate_heatmap(spo2_map)
    heatmap_pure_bar = add_colorbar(heatmap_pure)
    path_pure = out / "spo2_heatmap_pure.png"
    cv2.imwrite(str(path_pure), heatmap_pure_bar)

    heatmap_zones = overlay_risk_zones(heatmap_pure.copy(), spo2_map)
    heatmap_zones_bar = add_colorbar(heatmap_zones)
    path_zones = out / "spo2_heatmap_zones.png"
    cv2.imwrite(str(path_zones), heatmap_zones_bar)

    h, w = img_650.shape
    img650_color = cv2.cvtColor(img_650, cv2.COLOR_GRAY2BGR)
    img850_color = cv2.cvtColor(img_850, cv2.COLOR_GRAY2BGR)
    heatmap_resized = cv2.resize(heatmap_pure, (w, h))

    cv2.putText(img650_color, "650nm", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 2)
    cv2.putText(img850_color, "850nm", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 2)
    cv2.putText(heatmap_resized, "SpO2 Map", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)

    comparison = np.hstack([img650_color, img850_color, heatmap_resized])
    path_cmp = out / "comparison_strip.png"
    cv2.imwrite(str(path_cmp), comparison)

    paths = {"pure": path_pure, "zones": path_zones, "comparison": path_cmp}
    if print_report:
        print(f"Using pair: {p650.name} + {p850.name}")
        print("Saved:", ", ".join(str(p.name) for p in paths.values()))
    return paths


def main(pair: tuple[Path, Path] | None = None) -> None:
    p650, p850 = pair if pair is not None else find_latest_capture_pair()
    run_heatmaps((p650, p850), print_report=True)


if __name__ == "__main__":
    main()
