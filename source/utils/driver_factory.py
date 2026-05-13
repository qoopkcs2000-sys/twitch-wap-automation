"""Selenium WebDriver factory.

Centralizes how a browser session is built so test code never has to
care about ChromeOptions, mobile emulation flags, or driver binaries.
Switching to a different browser/grid/cloud provider becomes a one-file
change here.

Mobile emulation is configured by sending the same CDP commands that
Chrome's DevTools "Toggle Device Toolbar" issues. The legacy
``mobileEmulation`` capability is a thin shortcut that doesn't trigger
every mobile code path; many sites (Twitch included) only render the
full mobile UI after seeing the DevTools-style emulation parameters.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver

from config.settings import Settings
from utils.logger import get_logger

_logger = get_logger(__name__)


# Predefined mobile profiles. Add new entries here to support more
# devices; tests pick one via the ``MOBILE_DEVICE`` env var.
DEVICE_PROFILES: Dict[str, Dict[str, Any]] = {
    "Pixel 5": {
        "metrics": {
            "width": 393,
            "height": 851,
            "deviceScaleFactor": 2.75,
            "mobile": True,
        },
        "userAgent": (
            "Mozilla/5.0 (Linux; Android 13; Pixel 5) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Mobile Safari/537.36"
        ),
    },
    "iPhone 12 Pro": {
        "metrics": {
            "width": 390,
            "height": 844,
            "deviceScaleFactor": 3.0,
            "mobile": True,
        },
        "userAgent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/14.0 Mobile/15E148 Safari/604.1"
        ),
    },
    "Galaxy S20": {
        "metrics": {
            "width": 360,
            "height": 800,
            "deviceScaleFactor": 3.0,
            "mobile": True,
        },
        "userAgent": (
            "Mozilla/5.0 (Linux; Android 13; SM-G981B) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Mobile Safari/537.36"
        ),
    },
}


# Reduce the JS-side automation footprint. Injected before any page
# script runs so detection libraries see "real" mobile values.
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = window.chrome || { runtime: {} };
"""


# Auto-open DevTools alongside the browser so a human watching the run
# can verify the device toolbar is on. Toggle via env var; defaults to
# off so CI runs aren't bothered.
_OPEN_DEVTOOLS = os.getenv("OPEN_DEVTOOLS", "false").lower() in ("1", "true", "yes")


class DriverFactory:
    """Builds preconfigured WebDriver instances."""

    # ------------------------------------------------------------------
    # Profile resolution
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_profile(name: str) -> Dict[str, Any]:
        if name not in DEVICE_PROFILES:
            available = ", ".join(DEVICE_PROFILES)
            raise ValueError(
                f"Unknown mobile device '{name}'. Available profiles: {available}"
            )
        return DEVICE_PROFILES[name]

    # ------------------------------------------------------------------
    # Chrome options
    # ------------------------------------------------------------------
    @classmethod
    def _build_chrome_options(cls) -> Options:
        options = Options()

        # NOTE: ``useAutomationExtension`` and ``excludeSwitches`` were
        # removed because Chrome 127+ rejects them with
        # "cannot parse capability: goog:chromeOptions". We rely on
        # CDP-based emulation instead of the legacy ``mobileEmulation``
        # capability so the simulation is closer to what DevTools does
        # when you click "Toggle device toolbar".

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=en-US")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")

        # Make the browser window a comfortable size so the user can see
        # the entire emulated viewport plus DevTools (when enabled).
        profile = cls._resolve_profile(Settings.MOBILE_DEVICE)
        w, h = profile["metrics"]["width"], profile["metrics"]["height"]
        # Add headroom for browser chrome + optional DevTools panel.
        window_w = w + (520 if _OPEN_DEVTOOLS else 0)
        window_h = h + 200
        options.add_argument(f"--window-size={window_w},{window_h}")

        if _OPEN_DEVTOOLS:
            # Auto-open DevTools alongside the page on launch.
            options.add_argument("--auto-open-devtools-for-tabs")

        if Settings.HEADLESS:
            options.add_argument("--headless=new")

        return options

    # ------------------------------------------------------------------
    # CDP-based mobile emulation (the "DevTools way")
    # ------------------------------------------------------------------
    @classmethod
    def _apply_device_emulation(cls, driver: WebDriver) -> None:
        """Mimic clicking DevTools' "Toggle Device Toolbar" via CDP.

        Three commands match what Chrome runs internally when you flip
        device mode on:
          1. ``Network.setUserAgentOverride`` for UA + Accept-Language
          2. ``Emulation.setDeviceMetricsOverride`` for viewport
          3. ``Emulation.setTouchEmulationEnabled`` for touch events

        Setting them via CDP (rather than the legacy ``mobileEmulation``
        capability) is what makes Twitch render its full mobile UI,
        including the bottom navigation bar with the search icon.
        """
        profile = cls._resolve_profile(Settings.MOBILE_DEVICE)
        metrics = profile["metrics"]
        ua = profile["userAgent"]

        try:
            driver.execute_cdp_cmd(
                "Network.setUserAgentOverride",
                {
                    "userAgent": ua,
                    "acceptLanguage": "en-US,en;q=0.9",
                    "platform": "Linux armv8l",
                },
            )
            driver.execute_cdp_cmd(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": metrics["width"],
                    "height": metrics["height"],
                    "deviceScaleFactor": metrics["deviceScaleFactor"],
                    "mobile": metrics["mobile"],
                    "screenOrientation": {
                        "type": "portraitPrimary",
                        "angle": 0,
                    },
                },
            )
            driver.execute_cdp_cmd(
                "Emulation.setTouchEmulationEnabled",
                {"enabled": True, "maxTouchPoints": 5},
            )
            _logger.info(
                "CDP device emulation applied (%dx%d, mobile=%s)",
                metrics["width"], metrics["height"], metrics["mobile"],
            )
        except Exception as exc:
            _logger.warning("Could not apply CDP emulation: %s", exc)

    @classmethod
    def _apply_stealth(cls, driver: WebDriver) -> None:
        """Hide the most obvious automation tells from JS-side checks."""
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": _STEALTH_JS},
            )
            _logger.info("Stealth script installed")
        except Exception as exc:
            _logger.warning("Could not install stealth script: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @classmethod
    def create(cls, browser: str = "chrome") -> WebDriver:
        """Return a configured WebDriver.

        Uses Selenium Manager (built into Selenium 4.6+) to locate a
        compatible chromedriver, avoiding webdriver-manager cache
        mismatches when Chrome auto-updates.
        """
        browser = browser.lower()
        if browser != "chrome":
            raise NotImplementedError(f"Browser '{browser}' is not supported yet")

        _logger.info(
            "Starting Chrome (mobile profile='%s', headless=%s, devtools=%s)",
            Settings.MOBILE_DEVICE, Settings.HEADLESS, _OPEN_DEVTOOLS,
        )
        driver = webdriver.Chrome(options=cls._build_chrome_options())
        driver.set_page_load_timeout(Settings.PAGE_LOAD_TIMEOUT)

        # Order matters:
        #   1. stealth must run BEFORE any navigation
        #   2. emulation must be set BEFORE the first page load too
        cls._apply_stealth(driver)
        cls._apply_device_emulation(driver)
        return driver
