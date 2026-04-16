"""
OptiFoot — Point-of-Care Diabetic Foot Ulcer Early Detection
Main application entry point.

Usage:
    python -m optifoot.main           # normal mode (requires Raspberry Pi + camera)
    python -m optifoot.main --demo    # demo mode (synthetic images, runs on any machine)
"""

import argparse
import logging
import sys

from optifoot import config


def _parse_args():
    parser = argparse.ArgumentParser(
        description="OptiFoot — Diabetic Foot Ulcer Early Detection"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode with synthetic images (no hardware required)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity (default: INFO)",
    )
    parser.add_argument(
        "--override",
        choices=["0", "1"],
        default=None,
        help="Demo override: 1 = No Risk (>90%% blood flow), 0 = Risk Present (<5%% blood flow)",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("optifoot")

    # Apply demo mode
    if args.demo:
        config.DEMO_MODE = True
        log.info("Running in DEMO mode (synthetic images, no hardware)")

    # Apply demo override
    if args.override is not None:
        config.DEMO_OVERRIDE = args.override
        label = "No Risk (>90%%)" if args.override == "1" else "Risk Present (<5%%)"
        log.info("Demo override active: %s", label)

    # Import after config is set so factories read DEMO_MODE correctly
    from PyQt5.QtWidgets import QApplication
    from optifoot.pipeline import Pipeline
    from optifoot.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("OptiFoot")
    app.setStyle("Fusion")

    # Apply dark palette
    from PyQt5.QtGui import QPalette, QColor
    from PyQt5.QtCore import Qt

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
    palette.setColor(QPalette.ToolTipBase, QColor(50, 50, 50))
    palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(0, 212, 170))
    palette.setColor(QPalette.Highlight, QColor(13, 110, 110))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    # Build pipeline and GUI
    pipeline = Pipeline()
    pipeline.start()

    window = MainWindow(pipeline)
    window.show()

    log.info("OptiFoot ready")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
