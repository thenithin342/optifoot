#!/usr/bin/env python3
"""
Live preview + capture in a web UI. Run on the Raspberry Pi, then open in a browser on Windows:

    cd "/home/pi/New folder" && python3 capture_web_interface.py

On your PC: http://<PI_IP>:8765/   (or run: python open_pi_capture_ui.py)

Uses the same CaptureHardware as capture_two_images.py (650 nm + 850 nm on one button).
"""
from __future__ import annotations

import argparse
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

from capture_hardware import CaptureHardware

INDEX_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Pi live capture</title>
<style>
body{font-family:system-ui,Segoe UI,sans-serif;background:#121212;color:#eee;text-align:center;margin:20px}
h2{font-weight:600}
img{max-width:min(960px,96vw);height:auto;border:2px solid #333;border-radius:10px;background:#000}
button{font-size:1.05rem;padding:14px 28px;margin-top:18px;cursor:pointer;border-radius:10px;border:none;
background:#1d6b4a;color:#fff;font-weight:600}
button:disabled{opacity:0.45;cursor:wait}
#msg{margin-top:14px;color:#7ec8e3;min-height:2em;white-space:pre-wrap}
.hint{color:#888;font-size:0.9rem;margin-top:8px}
</style></head><body>
<h2>Live preview (Pi camera)</h2>
<img src="/stream" alt="live stream"/>
<p class="hint">Place the foot, then capture both wavelengths sequentially.</p>
<p id="msg"></p>
<button type="button" id="cap650" style="margin-right:12px; background:#c0392b;">Capture 650</button>
<button type="button" id="cap850" style="background:#555;">Capture 850</button>
<script>
const b6=document.getElementById("cap650"), b8=document.getElementById("cap850"), m=document.getElementById("msg");
const doCap = async (url, txt) => {
  b6.disabled=true; b8.disabled=true; m.textContent=txt;
  try {
    const r=await fetch(url,{method:"POST"});
    const t=await r.text();
    m.textContent=t.startsWith("OK")?("Saved on Pi:\\n"+t.substring(3).trim()):("Error: "+t);
  }catch(e){m.textContent="Network error: "+e;}
  finally{b6.disabled=false; b8.disabled=false;}
};
b6.onclick=()=>doCap("/capture/650", "Capturing 650...");
b8.onclick=()=>doCap("/capture/850", "Capturing 850...");
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    hw: CaptureHardware | None = None
    stream_lock: threading.Lock | None = None

    def log_message(self, format: str, *args) -> None:
        pass

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/stream":
            self._mjpeg_stream()
            return
        self.send_error(404)

    def _mjpeg_stream(self) -> None:
        assert self.hw is not None and self.stream_lock is not None
        self.send_response(200)
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Type", "multipart/x-mixed-replace; boundary=frame"
        )
        self.end_headers()
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        try:
            while True:
                jpg: bytes | None = None
                with self.stream_lock:
                    try:
                        yuv = self.hw.cam.capture_array("lores")
                        rgb = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB_I420)
                        rgb = cv2.resize(rgb, (640, 400))
                        ok, enc = cv2.imencode(
                            ".jpg", rgb, [int(cv2.IMWRITE_JPEG_QUALITY), 82]
                        )
                        if ok:
                            jpg = enc.tobytes()
                    except Exception:
                        pass
                if jpg:
                    try:
                        self.wfile.write(boundary + jpg + b"\r\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                time.sleep(0.06)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self) -> None:
        if self.path not in ("/capture/650", "/capture/850"):
            self.send_error(404)
            return
        assert self.hw is not None and self.stream_lock is not None
        try:
            with self.stream_lock:
                if self.hw.has_650 and self.hw.has_850:
                    self.hw.assign_next_pair_paths()
                
                if self.path == "/capture/650":
                    self.hw.start_650()
                    if not self.hw.capture_650():
                        raise RuntimeError("650 nm capture failed")
                    msg_name = self.hw.p650.name
                else:
                    self.hw.start_850()
                    if not self.hw.capture_850():
                        raise RuntimeError("850 nm capture failed")
                    msg_name = self.hw.p850.name

            msg = f"OK {msg_name}"
            body = msg.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            err = f"ERR {e}".encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)


def main() -> None:
    parser = argparse.ArgumentParser(description="Web UI for live Pi capture.")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default 8765)")
    parser.add_argument("--bind", default="0.0.0.0", help="Listen address")
    args = parser.parse_args()

    lock = threading.Lock()
    print("Starting camera (same hardware as capture_two_images.py)…")
    hw = CaptureHardware(for_gui=True)
    Handler.hw = hw
    Handler.stream_lock = lock

    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)

    def stop(*_: object) -> None:
        print("\nShutting down…")
        try:
            httpd.shutdown()
        except Exception:
            pass
        hw.shutdown()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print(f"Serving http://{args.bind}:{args.port}/")
    print("From Windows, open: http://<this-pi-ip>:%d/ in Chrome or Edge." % args.port)
    try:
        httpd.serve_forever()
    finally:
        hw.shutdown()


if __name__ == "__main__":
    main()
