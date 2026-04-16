#!/usr/bin/env python3
"""Dual-wavelength capture on Raspberry Pi: GUI (default) or headless --auto for SSH pipelines."""
from __future__ import annotations

import argparse

import cv2

from capture_hardware import CaptureHardware, run_auto_sequence


def _run_gui() -> int:
    import tkinter as tk
    from tkinter import messagebox

    from PIL import Image, ImageTk

    class App:
        def __init__(self, root):
            self.root = root
            self.root.title("Capture 650/850")
            self.root.geometry("920x680")

            self.hw = CaptureHardware(for_gui=True)
            self.running = True

            self.lbl = tk.Label(root, bg="black")
            self.lbl.pack(fill="both", expand=True, padx=10, pady=10)

            self.status = tk.StringVar(
                value="Live preview — position the foot, then press Capture (saves 650 nm + 850 nm)."
            )
            tk.Label(root, textvariable=self.status, wraplength=880).pack()

            row = tk.Frame(root)
            row.pack(pady=12)
            self.btn_capture = tk.Button(
                row,
                text="Capture 650 & 850",
                command=self.capture_both_wavelengths,
                font=("TkDefaultFont", 14, "bold"),
                padx=24,
                pady=10,
            )
            self.btn_capture.pack(side="left", padx=8)
            tk.Button(row, text="Exit", command=self.close, padx=12, pady=10).pack(side="left", padx=8)

            self.update_preview()
            self.root.protocol("WM_DELETE_WINDOW", self.close)

        def _pump_gui(self) -> None:
            self.root.update_idletasks()
            self.root.update()

        def capture_both_wavelengths(self) -> None:
            self.btn_capture.config(state="disabled")
            self._pump_gui()
            try:
                self.hw.assign_next_pair_paths()
                self.status.set("650 nm LED on — hold still…")
                self._pump_gui()
                self.hw.start_650()
                self._pump_gui()
                self.status.set("Capturing 650 nm…")
                self._pump_gui()
                if not self.hw.capture_650():
                    messagebox.showerror("Capture", "650 nm capture failed (wrong state).")
                    return
                self.status.set("850 nm LED on — hold still…")
                self._pump_gui()
                self.hw.start_850()
                self._pump_gui()
                self.status.set("Capturing 850 nm…")
                self._pump_gui()
                if not self.hw.capture_850():
                    messagebox.showerror("Capture", "850 nm capture failed (wrong state).")
                    return
                self.status.set(
                    "Done. Press Capture again for another pair, or Exit."
                )
                messagebox.showinfo(
                    "Saved",
                    f"650 nm:\n{self.hw.p650}\n\n850 nm:\n{self.hw.p850}",
                )
            finally:
                self.btn_capture.config(state="normal")

        def update_preview(self):
            if not self.running:
                return
            try:
                yuv = self.hw.cam.capture_array("lores")
                rgb = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB_I420)
                img = Image.fromarray(rgb).resize((640, 400))
                imgtk = ImageTk.PhotoImage(img)
                self.lbl.imgtk = imgtk
                self.lbl.configure(image=imgtk)
            except Exception:
                pass
            self.root.after(150, self.update_preview)

        def close(self):
            self.running = False
            self.hw.shutdown()
            self.root.destroy()

    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="650/850 dual capture (GUI or --auto).")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Headless: run full 650/850 capture then exit (for SSH from PC).",
    )
    args = parser.parse_args()
    if args.auto:
        return run_auto_sequence()
    return _run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
