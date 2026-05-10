"""Centralized configuration for the twitch-wap-automation framework.

Values can be overridden through environment variables to keep the code
free of environment-specific details. This makes it easy to run the same
suite locally, in Docker, or on a CI runner.
"""
from __future__ import annotations

import os
from pathlib import Path


class Settings:
    """Project-wide settings."""

    # --- URLs --------------------------------------------------------------
    BASE_URL: str = os.getenv("TWITCH_BASE_URL", "https://www.twitch.tv/")

    # --- Mobile emulation --------------------------------------------------
    # Chrome DevTools "deviceName" used by Selenium's mobileEmulation option.
    MOBILE_DEVICE: str = os.getenv("MOBILE_DEVICE", "Pixel 5")

    # --- Timeouts (seconds) -----------------------------------------------
    DEFAULT_TIMEOUT: int = int(os.getenv("DEFAULT_TIMEOUT", "15"))
    PAGE_LOAD_TIMEOUT: int = int(os.getenv("PAGE_LOAD_TIMEOUT", "30"))
    # Popup visibility checks are cheap polls — they should NOT block
    # for a long time when no popup is present. 1 s gives the page a
    # fighting chance to render an overlay without burning minutes
    # iterating through every locator on a clean page.
    POPUP_TIMEOUT: int = int(os.getenv("POPUP_TIMEOUT", "1"))

    # --- Browser flags -----------------------------------------------------
    HEADLESS: bool = os.getenv("HEADLESS", "false").lower() in ("1", "true", "yes")

    # --- Test data ---------------------------------------------------------
    SEARCH_QUERY: str = os.getenv("SEARCH_QUERY", "StarCraft II")
    SCROLL_TIMES: int = int(os.getenv("SCROLL_TIMES", "2"))

    # --- Filesystem paths --------------------------------------------------
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    SCREENSHOTS_DIR: Path = PROJECT_ROOT.parent / "screenshots"
    REPORTS_DIR: Path = PROJECT_ROOT.parent / "reports"
    LOGS_DIR: Path = PROJECT_ROOT.parent / "logs"
    RECORDINGS_DIR: Path = PROJECT_ROOT.parent / "recordings"

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create runtime directories if missing."""
        for path in (cls.SCREENSHOTS_DIR, cls.REPORTS_DIR, cls.LOGS_DIR, cls.RECORDINGS_DIR):
            path.mkdir(parents=True, exist_ok=True)
