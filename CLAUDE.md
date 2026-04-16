# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OptiFoot — Point-of-care diabetic foot ulcer early detection system using dual-wavelength NIR imaging. Runs on Raspberry Pi with camera module, or in demo mode on any machine.

## Commands

```bash
# Run GUI (demo mode without hardware)
python -m optifoot.main --demo

# Run GUI with demo override (force specific output)
python -m optifoot.main --demo --override 1  # No Risk (>90%)
python -m optifoot.main --demo --override 0  # Risk Present (<5%)

# Generate demo outputs for presentations
python demo_midsem.py

# Run tests
pytest optifoot/tests/
pytest optifoot/tests/test_oxygenation.py -v  # single test file

# Install dependencies
pip install -r optifoot/requirements.txt

# **Recommended — live preview in browser, you click Capture, then HTML report opens (Windows)**
python live_capture_session.py
# Requires on Pi: `capture_hardware.py`, `capture_web_interface.py`, `capture_two_images.py` in the same folder (upload_to_pi.py sends all three). Port 8765 must reach the PC (Pi firewall).

# Headless: Pi runs --auto capture, download 2 PNGs, analyze, open HTML report (no live UI)
python pull_and_process.py
# Skip opening browser: PULL_NO_OPEN=1 python pull_and_process.py

# Download **all** captures from Pi (bulk backup), then analyze latest pair locally
python download_from_pi.py
python analyze_capture.py

# Push capture scripts to Pi only
python upload_to_pi.py

# Open Pi web UI only (you must already run `python3 capture_web_interface.py` on the Pi)
python open_pi_capture_ui.py
```

## Architecture

```
optifoot/
├── main.py              # Entry point, argparse, PyQt5 app setup
├── config.py            # GPIO pins, camera settings, SpO2 thresholds, extinction coefficients
├── pipeline.py          # Orchestrates: capture → preprocess → SpO2 → heatmap → risk score
├── capture/
│   ├── camera.py        # NIRCamera (PiCamera2) + DemoCamera (factory pattern)
│   └── led_controller.py # LEDController (gpiozero) + DemoLEDController
├── processing/
│   ├── preprocessing.py # Gaussian blur, ECC image alignment, Otsu foot masking
│   ├── oxygenation.py   # Beer-Lambert SpO2 calculation from 650nm/850nm ratio
│   └── heatmap.py       # JET colormap, risk zone contours, colorbar
├── analysis/
│   ├── risk_scorer.py   # ThresholdScorer (strategy pattern, extensible to MLScorer)
│   └── temporal.py      # Compare sequential scans, diff heatmaps
├── storage/
│   └── database.py      # SQLite: patients + scans tables, WAL mode
├── gui/
│   ├── main_window.py   # PyQt5 shell with toolbar, tabs, status bar
│   ├── capture_tab.py   # Image capture UI
│   ├── results_tab.py   # Heatmap display, risk panel
│   └── history_tab.py   # Scan history browser
└── tests/               # pytest tests for core modules
```

## Key Patterns

**Factory pattern**: Camera and LED controller use factories that return real hardware implementations on Pi, demo stubs otherwise. Check `config.DEMO_MODE` flag.

**Strategy pattern**: `RiskScorer` interface allows swapping `ThresholdScorer` for future `MLScorer` without pipeline changes.

**Dual-wavelength imaging**: Sequential capture under 650nm (red) and 850nm (NIR) illumination. SpO2 calculated per-pixel using Beer-Lambert law:
```
R = ln(I_650) / ln(I_850)
SpO2 = (ε_HHb_850 - R·ε_HHb_650) / ((ε_HHb_850 - ε_HbO2_850) - R·(ε_HHb_650 - ε_HbO2_650))
```

**Risk thresholds**:
- ≥95%: Normal
- 90-95%: Monitor  
- 85-90%: At Risk
- <85%: Critical

Composite risk score (0-100) weights: mean SpO2 (35%), critical area (30%), at-risk area (20%), cluster size (15%).

## Data Flow

1. LED controller activates 650nm LED → camera captures → LED off
2. LED controller activates 850nm LED → camera captures → LED off
3. Preprocessing: blur, align 850nm to 650nm (ECC), create foot mask (Otsu + morphology)
4. SpO2 map: Beer-Lambert calculation on masked foot region
5. Heatmap: JET colormap with risk zone contour overlays
6. Risk score: threshold-based classification + composite score
7. Persistence: save to SQLite with patient ID, retrieve via history tab

## Demo Mode

Set `config.DEMO_MODE = True` or use `--demo` flag. DemoCamera generates synthetic foot-shaped regions with plausible SpO2 contrast. Demo override (`--override 0|1`) forces specific risk outputs for presentations.
