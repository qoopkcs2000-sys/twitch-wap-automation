"""Base page object.

Every concrete page inherits from :class:`BasePage`. It encapsulates the
WebDriver and exposes safe wrappers around common Selenium calls so test
authors never have to instantiate WebDriverWait or expected_conditions
in their own code.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Tuple

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config.settings import Settings
from utils.logger import get_logger

Locator = Tuple[str, str]


class BasePage:
    """Common helpers shared by every page object."""

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(driver, Settings.DEFAULT_TIMEOUT)
        self.logger = get_logger(self.__class__.__name__)

    # -- Navigation ---------------------------------------------------------
    def open(self, url: str) -> "BasePage":
        self.logger.info("Opening URL: %s", url)
        self.driver.get(url)
        return self

    # -- Element lookup -----------------------------------------------------
    def _wait(self, timeout: int | None = None) -> WebDriverWait:
        return WebDriverWait(self.driver, timeout or Settings.DEFAULT_TIMEOUT)

    def find(self, locator: Locator, timeout: int | None = None) -> WebElement:
        return self._wait(timeout).until(EC.presence_of_element_located(locator))

    def find_clickable(self, locator: Locator, timeout: int | None = None) -> WebElement:
        return self._wait(timeout).until(EC.element_to_be_clickable(locator))

    def find_visible(self, locator: Locator, timeout: int | None = None) -> WebElement:
        return self._wait(timeout).until(EC.visibility_of_element_located(locator))

    def is_visible(self, locator: Locator, timeout: int = 5) -> bool:
        try:
            self._wait(timeout).until(EC.visibility_of_element_located(locator))
            return True
        except TimeoutException:
            return False

    # -- Actions ------------------------------------------------------------
    def click(self, locator: Locator, timeout: int | None = None) -> None:
        self.find_clickable(locator, timeout).click()

    def type_text(self, locator: Locator, text: str, clear: bool = True,
                  timeout: int | None = None) -> WebElement:
        element = self.find_visible(locator, timeout)
        if clear:
            element.clear()
        element.send_keys(text)
        return element

    def scroll_down(self, times: int = 1, pause: float = 1.0) -> "BasePage":
        """Scroll one viewport at a time. Done in JS so it works
        consistently in mobile emulation."""
        for i in range(times):
            self.driver.execute_script("window.scrollBy(0, window.innerHeight);")
            self.logger.debug("Scrolled %d/%d", i + 1, times)
            time.sleep(pause)
        return self

    # -- Diagnostics --------------------------------------------------------
    def take_screenshot(self, name: str) -> Path:
        Settings.ensure_dirs()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Settings.SCREENSHOTS_DIR / f"{name}_{timestamp}.png"
        self.driver.save_screenshot(str(path))
        self.logger.info("Screenshot saved: %s", path)
        return path
