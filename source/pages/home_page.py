"""Twitch mobile home page."""
from __future__ import annotations

import time

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By

from config.settings import Settings
from pages.base_page import BasePage


class HomePage(BasePage):
    """Mobile home page (https://www.twitch.tv on a phone viewport)."""

    URL = Settings.BASE_URL

    # The mobile site shows an "Open in App / Keep using web" sheet on
    # first visit. We have to dismiss it before any navigation works.
    KEEP_USING_WEB_BUTTONS = [
        (By.XPATH, "//button[normalize-space()='Keep using web']"),
        (By.XPATH, "//a[normalize-space()='Keep using web']"),
        (By.XPATH, "//*[contains(translate(., 'KEEP', 'keep'), 'keep using web')]"),
    ]

    # Twitch has shipped several variants of the search affordance over
    # time. The current m.twitch.tv layout puts the magnifying glass
    # in the bottom tab bar (labelled "Browse"/"瀏覽") and links to
    # ``/directory``. We try that first — it's by far the most common
    # current shape — then fall back to header variants.
    SEARCH_ICON_LOCATORS = [
        # Explicit labels are the most reliable
        (By.CSS_SELECTOR, "a[aria-label*='Browse' i]"),
        (By.CSS_SELECTOR, "a[aria-label*='Search' i]"),
        (By.CSS_SELECTOR, "a[aria-label*='瀏覽']"),
        (By.CSS_SELECTOR, "a[aria-label*='搜尋']"),
        # Strict href matches
        (By.CSS_SELECTOR, "a[href='/directory']"),
        (By.CSS_SELECTOR, "a[href='/search']"),
        # Fallbacks
        (By.CSS_SELECTOR, "[data-a-target='search-button']"),
        (By.XPATH, "//a[contains(@href, '/directory') and not(contains(@href, 'following'))]"),
        (By.XPATH, "//a[contains(@href, '/search')]"),
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load(self) -> "HomePage":
        # Twitch keeps fetching telemetry / ads / chat WebSockets long
        # after the visible page is interactive, so plain ``driver.get``
        # often hits PAGE_LOAD_TIMEOUT even when the UI is fully usable.
        # We catch that timeout, abort the load with window.stop(), and
        # carry on as long as the document body is present.
        try:
            self.open(self.URL)
            # Extra insurance: force Twitch into mobile mode via cookie
            # Must be set AFTER opening the domain.
            try:
                self.driver.execute_script(
                    "document.cookie = 'tw-device-type=mobile; path=/; domain=.twitch.tv';"
                )
                self.logger.info("Mobile device cookie injected")
            except Exception as e:
                self.logger.warning("Could not inject mobile cookie: %s", e)
        except (TimeoutException, WebDriverException) as exc:
            self.logger.warning(
                "driver.get() timed out (%s) — aborting pending requests "
                "and continuing", exc.__class__.__name__,
            )
            try:
                self.driver.execute_script("window.stop();")
            except Exception:
                pass

        # Wait for the body to exist; that's enough to start interacting.
        self.find((By.TAG_NAME, "body"), timeout=Settings.DEFAULT_TIMEOUT)
        self.logger.info("Twitch home page reached (current_url=%s)", self.driver.current_url)

        # We return immediately. dismiss_app_prompt() will be called 
        # on-demand if it intercepts the search icon click.
        return self

    def dismiss_app_prompt(self) -> "HomePage":
        """Close the "Open in App" sheet that mobile Twitch shows on
        first load. Safe to call when the sheet is not present.

        Tries CSS click first, then JavaScript click as a fallback —
        the sheet sometimes intercepts pointer events and a normal
        click silently no-ops.
        """
        for locator in self.KEEP_USING_WEB_BUTTONS:
            if not self.is_visible(locator, timeout=3):
                continue
            try:
                self.click(locator, timeout=3)
                self.logger.info("Dismissed 'Open in App' prompt via %s", locator)
                time.sleep(1)
                return self
            except Exception as exc:
                self.logger.warning(
                    "Native click failed (%s); trying JS click", exc.__class__.__name__,
                )
                try:
                    element = self.find(locator, timeout=3)
                    self.driver.execute_script("arguments[0].click();", element)
                    self.logger.info("Dismissed via JS click: %s", locator)
                    time.sleep(1)
                    return self
                except Exception as js_exc:
                    self.logger.warning("JS click also failed: %s", js_exc)
        self.logger.info("No 'Open in App' prompt detected (or could not dismiss)")
        return self

    def open_search(self) -> "SearchPage":  # noqa: F821 - forward ref
        """Locate and click the search/browse icon to navigate to the search page.

        Attempts to find the search affordance using multiple known locators.
        If a click is intercepted, it automatically attempts to dismiss 
        the 'Open in App' prompt and retries.
        """
        self.logger.info("Looking for the search icon eagerly")
        
        deadline = time.monotonic() + Settings.DEFAULT_TIMEOUT
        last_exc: Exception | None = None
        
        while time.monotonic() < deadline:
            for locator in self.SEARCH_ICON_LOCATORS:
                if not self.is_visible(locator, timeout=0.5):
                    continue
                try:
                    # Try to click the icon directly
                    element = self.find_clickable(locator, timeout=1)
                    element.click()
                    self.logger.info("Search icon clicked via %s", locator)
                    from pages.search_page import SearchPage
                    return SearchPage(self.driver)
                except Exception as exc:
                    self.logger.debug("Click on %s failed/intercepted; checking for app prompt", locator)
                    # If click failed, it might be the app prompt overlaying the icon
                    self.dismiss_app_prompt()
                    last_exc = exc
            
            time.sleep(0.5)

        raise AssertionError(
            f"Could not click any known search icon locator within timeout. "
            f"Last error: {last_exc}"
        )
