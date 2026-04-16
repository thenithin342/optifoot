"""
OptiFoot Configuration
Central configuration for GPIO pins, camera settings, SpO2 thresholds,
and Beer-Lambert extinction coefficients.
"""

# ---------------------------------------------------------------------------
# GPIO Pin Assignments (BCM numbering)
# ---------------------------------------------------------------------------
LED_650NM_PIN = 17          # Red 650 nm high-power LED
LED_850NM_PIN = 27          # NIR 850 nm high-power LED
LED_STABILIZE_DELAY = 0.08  # seconds to wait after LED switch (80 ms)

# ---------------------------------------------------------------------------
# Camera Settings  (Raspberry Pi Camera Module 3 NoIR)
# ---------------------------------------------------------------------------
CAMERA_RESOLUTION = (1640, 1232)
CAMERA_FORMAT = "main"
EXPOSURE_TIME_US = 20000    # fixed exposure in microseconds
ANALOGUE_GAIN = 4.0         # fixed analogue gain for NIR sensitivity
AWB_ENABLE = False          # disable auto white balance for consistency

# ---------------------------------------------------------------------------
# SpO2 Risk Thresholds (%)
# ---------------------------------------------------------------------------
SPO2_NORMAL_MIN = 95.0      # >=95 → Normal
SPO2_MONITOR_MIN = 90.0     # 90-95 → Monitor
SPO2_AT_RISK_MIN = 85.0     # 85-90 → At Risk
                             # <85  → Critical

# Risk score weights for composite scoring
WEIGHT_MEAN_SPO2 = 0.35
WEIGHT_CRITICAL_AREA = 0.30
WEIGHT_AT_RISK_AREA = 0.20
WEIGHT_CLUSTER_SIZE = 0.15

# ---------------------------------------------------------------------------
# Beer-Lambert Extinction Coefficients (cm⁻¹·(mol/L)⁻¹)
# Literature values for oxygenated (HbO2) and deoxygenated (HHb) hemoglobin
# Source: Prahl, "Tabulated Molar Extinction Coefficient for Hemoglobin"
# ---------------------------------------------------------------------------
EPSILON_HBO2_650 = 0.0081   # ε HbO₂ at 650 nm (low absorption)
EPSILON_HBO2_850 = 0.0234   # ε HbO₂ at 850 nm (higher absorption)
EPSILON_HHB_650 = 0.0367    # ε HHb  at 650 nm (high absorption)
EPSILON_HHB_850 = 0.0177    # ε HHb  at 850 nm (lower absorption)

# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------
GAUSSIAN_BLUR_SIGMA = 1.5   # σ for noise-reduction Gaussian blur
MORPH_KERNEL_SIZE = 7       # kernel for morphological operations in foot mask
MIN_FOOT_AREA_RATIO = 0.05  # minimum fraction of image that must be foot

# ---------------------------------------------------------------------------
# File Paths
# ---------------------------------------------------------------------------
import os as _os

DATA_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data")
DB_PATH = _os.path.join(DATA_DIR, "optifoot.db")
SCANS_DIR = _os.path.join(DATA_DIR, "scans")
CALIBRATION_DIR = _os.path.join(DATA_DIR, "calibration")

# Ensure directories exist at import time
for _d in (DATA_DIR, SCANS_DIR, CALIBRATION_DIR):
    _os.makedirs(_d, exist_ok=True)

# ---------------------------------------------------------------------------
# Demo / Development Mode
# ---------------------------------------------------------------------------
DEMO_MODE = False           # overridden by --demo CLI flag
DEMO_OVERRIDE = None        # set to "1" (No Risk) or "0" (Risk) for demo output override
