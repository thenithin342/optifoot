"""
Fully automated headless pipeline (no browser capture):

1. Upload + run `capture_two_images.py --auto` on the Pi
2. Download only this run's two PNGs → ./captures
3. Analysis + heatmaps + **HTML report** (opens in browser on Windows)

For **live** preview and you choose when to capture, use instead:

    python live_capture_session.py
"""
from __future__ import annotations

import os
import webbrowser

import analyze_capture
import generate_heatmaps
from pi_sync import download_capture_basenames, run_remote_auto_capture
from project_paths import CAPTURES_DIR
from scan_report_html import write_scan_report


def main() -> None:
    print("=== 1) Pi: upload script + automated 650/850 capture ===\n")
    exit_code, remote_log, basenames = run_remote_auto_capture()
    print(remote_log.rstrip() or "(no remote output)")
    if exit_code != 0:
        raise SystemExit(
            f"Remote capture failed with exit code {exit_code}. "
            "Check Pi is on, SSH works, camera/GPIO available, and log above."
        )
    if basenames is None:
        raise SystemExit(
            "Capture ran but AUTO_CAPTURE_OK line was not found in Pi output; "
            "cannot download this run only. Is capture_two_images.py updated on the Pi?"
        )

    b650, b850 = basenames
    print("\n=== 2) Download this capture only (2 files) ===\n")
    pair = download_capture_basenames(b650, b850)

    print("\n=== 3) Analysis + heatmaps + HTML report ===\n")
    analysis = analyze_capture.analyze_pair(pair, out_dir=CAPTURES_DIR, print_report=True)
    hm = generate_heatmaps.run_heatmaps(pair, out_dir=CAPTURES_DIR, print_report=True)

    report_path = CAPTURES_DIR / f"report_{analysis['pair_id']}.html"
    image_paths = {
        "raw650": pair[0],
        "raw850": pair[1],
        "analysis_heatmap": CAPTURES_DIR / "analysis_heatmap.png",
        "zones": hm["zones"],
        "comparison": hm["comparison"],
    }
    write_scan_report(report_path, analysis=analysis, image_paths=image_paths)

    if os.environ.get("PULL_NO_OPEN", "").strip() not in ("1", "true", "yes"):
        print(f"\nOpening report: {report_path}")
        webbrowser.open(report_path.resolve().as_uri())

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
