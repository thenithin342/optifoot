"""
Open the Pi live-capture web page in your default browser (Windows / any OS).

Prerequisite on the Pi (SSH or VNC terminal):

    cd "/home/pi/New folder" && python3 capture_web_interface.py

Then run on your PC:

    python open_pi_capture_ui.py

Env: PI_HOST (default from pi_sync), PI_CAPTURE_PORT (default 8765).
"""
from __future__ import annotations

import os
import webbrowser


def main() -> None:
    host = os.environ.get("PI_HOST", "10.66.136.37")
    port = os.environ.get("PI_CAPTURE_PORT", "8765")
    url = f"http://{host}:{port}/"
    print(f"Opening: {url}")
    print('If the page fails to load, start the server on the Pi:')
    print('  cd "/home/pi/New folder" && python3 capture_web_interface.py')
    webbrowser.open(url)


if __name__ == "__main__":
    main()
