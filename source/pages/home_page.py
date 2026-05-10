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
        # Current m.twitch.tv bottom-nav (most common, try first)
        (By.CSS_SELECTOR, "a[href='/directory']"),
        (By.CSS_SELECTOR, "a[href^='/directory']"),
        (By.CSS_SELECTOR, "a[aria-label*='Browse' i]"),
        (By.CSS_SELECTOR, "a[aria-label*='瀏覽']"),
        (By.XPATH, "//a[contains(@href, '/directory')]"),
        # Header / legacy variants
        (By.CSS_SELECTOR, "a[href='/search']"),
        (By.CSS_SELECTOR, "a[href^='/search']"),
        (By.CSS_SELECTOR, "button[aria-label*='Search' i]"),
        (By.CSS_SELECTOR, "a[aria-label*='Search' i]"),
        (By.CSS_SELECTOR, "[data-a-target='search-button']"),
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
        self.logger.info("Twitch home page loaded (current_url=%s)", self.driver.current_url)

        # Twitch's mobile UI is heavily client-rendered; give it a
        # moment to settle before we start hunting elements.
        time.sleep(3)
        self.dismiss_app_prompt()
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
        """Strictly perform "click in the search icon" (assignment step 2).

        We try every known locator variant for the search/browse icon
        in turn. If none is clickable we raise — we do **not** fall
        back to direct URL navigation, because the assignment requires
        an explicit click on the icon.
        """
        self.logger.info("Looking for the search icon")
        last_exc: Exception | None = None
        # First locator gets a generous wait (page may still be
        # rendering); subsequent locators are short polls so we don't
        # burn 3 seconds on every miss.
        for i, locator in enumerate(self.SEARCH_ICON_LOCATORS):
            timeout = 5 if i == 0 else 1
            if not self.is_visible(locator, timeout=timeout):
                continue
            try:
                element = self.find_clickable(locator, timeout=3)
                aria = element.get_attribute("aria-label") or ""
                title = element.get_attribute("title") or ""
                self.logger.info(
                    "Clicking search icon — locator=%s aria-label=%r title=%r",
                    locator, aria, title,
                )
                element.click()
                self.logger.info("Search icon clicked via %s", locator)
                from pages.search_page import SearchPage
                return SearchPage(self.driver)
            except Exception as exc:
                self.logger.warning("Failed to click %s: %s", locator, exc)
                last_exc = exc

        raise AssertionError(
            "Could not click any known search icon locator. "
            f"Last error: {last_exc}"
        )
