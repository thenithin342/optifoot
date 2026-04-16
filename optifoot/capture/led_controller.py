"""
LED Controller for dual-wavelength illumination.

Controls the 650 nm (red) and 850 nm (NIR) high-power LEDs via GPIO.
Includes a DemoLEDController that logs actions for laptop development.
"""

import time
import logging
from abc import ABC, abstractmethod

from optifoot import config

log = logging.getLogger(__name__)


class BaseLEDController(ABC):
    """Interface that both real and demo controllers implement."""

    @abstractmethod
    def activate_650nm(self) -> None: ...

    @abstractmethod
    def activate_850nm(self) -> None: ...

    @abstractmethod
    def all_off(self) -> None: ...

    def close(self) -> None:
        self.all_off()

    # Context-manager support for safe GPIO cleanup
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class LEDController(BaseLEDController):
    """Real GPIO controller using gpiozero (Raspberry Pi only)."""

    def __init__(self):
        from gpiozero import LED as _LED          # import here – fails gracefully on non-Pi
        self._led_650 = _LED(config.LED_650NM_PIN)
        self._led_850 = _LED(config.LED_850NM_PIN)
        self.all_off()
        log.info("LEDController initialised (GPIO %s / %s)",
                 config.LED_650NM_PIN, config.LED_850NM_PIN)

    def activate_650nm(self) -> None:
        self._led_850.off()
        self._led_650.on()
        time.sleep(config.LED_STABILIZE_DELAY)
        log.debug("650 nm LED ON")

    def activate_850nm(self) -> None:
        self._led_650.off()
        self._led_850.on()
        time.sleep(config.LED_STABILIZE_DELAY)
        log.debug("850 nm LED ON")

    def all_off(self) -> None:
        self._led_650.off()
        self._led_850.off()
        log.debug("All LEDs OFF")

    def close(self) -> None:
        self.all_off()
        self._led_650.close()
        self._led_850.close()
        log.info("LEDController closed")


class DemoLEDController(BaseLEDController):
    """Stub controller that just logs — for testing without hardware."""

    def __init__(self):
        log.info("[DEMO] LEDController initialised (no GPIO)")

    def activate_650nm(self) -> None:
        time.sleep(0.01)  # tiny delay to mimic real behaviour
        log.debug("[DEMO] 650 nm LED ON")

    def activate_850nm(self) -> None:
        time.sleep(0.01)
        log.debug("[DEMO] 850 nm LED ON")

    def all_off(self) -> None:
        log.debug("[DEMO] All LEDs OFF")


def create_led_controller() -> BaseLEDController:
    """Factory: returns real controller on Pi, demo controller otherwise."""
    if config.DEMO_MODE:
        return DemoLEDController()
    try:
        return LEDController()
    except Exception:
        log.warning("GPIO unavailable — falling back to DemoLEDController")
        return DemoLEDController()
