"""
One Windows command: full live-capture pipeline.

1. Upload capture scripts to the Pi
2. Start the Pi web UI (live preview + Capture button)
3. Open that page in your browser — click **Capture 650 & 850** when ready
4. Wait for the new PNGs on the Pi, download them into ./scans/session_…/
5. Run analysis + heatmaps and build a single **HTML report** (embedded images)
6. Open the report in your browser and stop the Pi web server

Usage (from repo root):

    python live_capture_session.py

Env: PI_HOST, PI_USER, PI_PASSWORD, PI_CAPTURE_PORT (default 8765).
"""
from __future__ import annotations

import os
import webbrowser
from datetime import datetime
from pathlib import Path

from analyze_capture import analyze_pair
from generate_heatmaps import run_heatmaps
from pi_sync import (
    download_capture_basenames,
    list_remote_capture_basenames,
    restart_remote_capture_web,
    stop_remote_capture_web,
    upload_pi_capture_bundle,
    wait_for_http_ready,
    wait_for_new_capture_pair,
)
from project_paths import REPO_ROOT
from scan_report_html import write_scan_report


def main() -> None:
    host = os.environ.get("PI_HOST", "10.66.136.37")
    port = int(os.environ.get("PI_CAPTURE_PORT", "8765"))
    live_url = f"http://{host}:{port}/"

    print("=== OptiFoot — live capture from Windows ===\n")
    print("Uploading Pi scripts (camera + web UI)…")
    upload_pi_capture_bundle()

    before = list_remote_capture_basenames()
    print("Restarting web UI on the Pi…")
    try:
        restart_remote_capture_web(port)
    except RuntimeError as e:
        raise SystemExit(str(e)) from e

    print(f"Waiting for Pi web UI ({live_url})…")
    wait_for_http_ready(host, port)

    print("\nOpening **live capture** in your browser.")
    webbrowser.open(live_url)
    print(
        "\n>>> In the browser: position the foot, then click **Capture 650**, and then **Capture 850**.\n"
        ">>> This program waits until both images appear on the Pi...\n"
    )

    try:
        b650, b850 = wait_for_new_capture_pair(before, timeout_sec=900.0)
    except TimeoutError as e:
        stop_remote_capture_web()
        raise SystemExit(str(e)) from e

    session = REPO_ROOT / "scans" / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    session.mkdir(parents=True, exist_ok=True)

    print("  Stopping Pi camera stream...")
    stop_remote_capture_web()

    print(f"\nDownloading new capture ->\n  {session}")
    pair = download_capture_basenames(b650, b850, local_dir=session)

    print("\n" + "="*50)
    print("SpO2 Calculation Mode:")
    print("  [1] No risk (86-96% SpO2)")
    print("  [0] High risk (2-8% SpO2)")
    print("  [Enter] Normal calculation")
    choice = input("Select mode (1/0) or press Enter to skip: ").strip()
    mock_mode = None
    if choice == "1":
        mock_mode = 1
    elif choice == "0":
        mock_mode = 0
    print("="*50 + "\n")

    print("Computing SpO2 map, risk score, and heatmaps...")
    analysis = analyze_pair(pair, out_dir=session, print_report=False, mock_mode=mock_mode)
    hm = run_heatmaps(pair, out_dir=session, print_report=False, mock_mode=mock_mode)

    report_path = session / "report.html"
    image_paths = {
        "raw650": pair[0],
        "raw850": pair[1],
        "analysis_heatmap": session / "analysis_heatmap.png",
        "zones": hm["zones"],
        "comparison": hm["comparison"],
    }
    write_scan_report(report_path, analysis=analysis, image_paths=image_paths)

    print("\nOpening **HTML report** in your browser.")
    webbrowser.open(report_path.resolve().as_uri())

    print(
        f"\nFinished.\n"
        f"  Session folder: {session}\n"
        f"  Report file:    {report_path}\n"
        f"  (Pi camera and server gracefully stopped.)\n"
    )


if __name__ == "__main__":
    main()
