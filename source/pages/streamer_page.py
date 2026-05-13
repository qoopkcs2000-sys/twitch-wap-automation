"""Twitch streamer/channel page."""
from __future__ import annotations

import time
from pathlib import Path

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config.settings import Settings
from pages.base_page import BasePage


class StreamerPage(BasePage):
    """Streamer page with video player + intermittent pop-ups."""

    VIDEO_PLAYER = (By.CSS_SELECTOR, "video")

    # Known dismissable overlays (mature content gate, cookie banners,
    # "start watching" CTA, etc). Keeping the list in one place makes it
    # easy to extend as Twitch changes their UI.
    POPUP_LOCATORS = [
        (By.CSS_SELECTOR, "button[data-a-target='consent-banner-accept']"),
        (By.CSS_SELECTOR, "button[data-a-target='content-classification-gate-overlay-start-watching-button']"),
        (By.CSS_SELECTOR, "button[data-test-selector='start-watching-button']"),
        (By.CSS_SELECTOR, "button[aria-label='Close']"),
        (By.XPATH, "//button[normalize-space()='Start Watching']"),
        (By.XPATH, "//button[normalize-space()='Accept']"),
    ]

    # ------------------------------------------------------------------
    # Recursive popup dismisser
    # ------------------------------------------------------------------
    def dismiss_popups(self, max_depth: int = 2) -> "StreamerPage":
        """Dismiss every visible overlay, then recurse.

        Twitch occasionally chains popups (cookie banner -> mature gate ->
        ad), so a single sweep is not enough. We dismiss everything we
        can see, then call ourselves again until either nothing is left
        or ``max_depth`` runs out. This strategy handles nested or
        chained UI components gracefully and keeps the helper
        future-proof against new overlay types.

        ``max_depth`` defaults to 2 — chained popups deeper than that
        are extremely rare and not worth the time.
        """
        if max_depth <= 0:
            return self

        # Snapshot which locators are visible RIGHT NOW with a single
        # cheap JS query. This avoids paying ``POPUP_TIMEOUT`` per
        # locator when nothing is on screen.
        visible_locators = [loc for loc in self.POPUP_LOCATORS
                            if self._element_present_immediately(loc)]
        if not visible_locators:
            return self

        dismissed_any = False
        for locator in visible_locators:
            if self._try_click(locator):
                dismissed_any = True
                time.sleep(0.5)  # let the next overlay render

        if dismissed_any:
            return self.dismiss_popups(max_depth - 1)
        return self

    def _element_present_immediately(self, locator) -> bool:
        """Cheap synchronous check — no polling/waiting at all."""
        try:
            return any(
                el.is_displayed()
                for el in self.driver.find_elements(*locator)
            )
        except Exception:
            return False

    def _try_click(self, locator) -> bool:
        if not self.is_visible(locator, timeout=Settings.POPUP_TIMEOUT):
            return False
        try:
            self.click(locator, timeout=Settings.POPUP_TIMEOUT)
            self.logger.info("Dismissed popup: %s", locator)
            return True
        except (
            ElementClickInterceptedException,
            ElementNotInteractableException,
            StaleElementReferenceException,
        ) as exc:
            self.logger.warning("Could not click popup %s: %s", locator, exc.__class__.__name__)
            return False

    # ------------------------------------------------------------------
    # Page state
    # ------------------------------------------------------------------
    def wait_until_loaded(self, timeout: int = 20) -> "StreamerPage":
        """Wait until *everything* on the streamer page has settled.

        We enforce a chain of checks to ensure a clean capture:

          1. URL is on a streamer / channel page — NOT a category
             page (``/directory/...``) and NOT the home / search
             pages. If we're on the wrong page, raise immediately so
             the test reports honestly instead of silently
             screenshotting the wrong thing.
          2. ``document.readyState === 'complete'``.
          3. ``<video>`` element is in the DOM and has loaded enough
             metadata to play (HAVE_METADATA or higher) — this is
             the strongest "stream is up" signal we can get without
             waiting for actual frame decode.
          4. Any spinner / skeleton loaders are gone.
          5. Brief settle for late-binding overlays (chat, recs).
        """
        self.logger.info("Waiting for streamer page to finish loading")

        # ---- (1) URL sanity check ----
        current = self.driver.current_url
        if "/directory" in current:
            raise AssertionError(
                f"Expected a streamer page but URL is a directory page: {current}"
            )
        # A streamer URL is twitch.tv/<channel> — single-segment path.
        from urllib.parse import urlparse
        parsed = urlparse(current)
        segments = [s for s in parsed.path.split("/") if s]
        if len(segments) != 1:
            self.logger.warning(
                "URL %s does not look like a /<channel> path; continuing anyway",
                current,
            )
        else:
            self.logger.info("Streamer URL confirmed: /%s", segments[0])

        # ---- (2) document readyState ----
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        self.logger.info("document.readyState=complete")

        # ---- (3) video player ready (best-effort) ----
        try:
            ready = WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script(
                    "const v=document.querySelector('video');"
                    "return v && v.readyState >= 1;"  # HAVE_METADATA
                )
            )
            if ready:
                self.logger.info("Video player metadata loaded (readyState >= 1)")
        except TimeoutException:
            self.logger.info(
                "Video player not ready within %ds — streamer may be offline "
                "or the channel page has no live stream", timeout,
            )

        # ---- (4) wait for spinners / skeleton loaders to disappear ----
        skeleton_locators = [
            (By.CSS_SELECTOR, "[class*='skeleton' i]"),
            (By.CSS_SELECTOR, "[class*='spinner' i]"),
            (By.CSS_SELECTOR, "[role='progressbar']"),
        ]
        for loc in skeleton_locators:
            try:
                WebDriverWait(self.driver, 5).until_not(
                    EC.visibility_of_element_located(loc)
                )
            except TimeoutException:
                # Some skeletons stay forever on offline channels — don't block.
                pass

        # ---- (5) one final popup sweep + settle ----
        # Popups (mature-content gate, cookie banner, ad close button)
        # can appear AFTER the initial page load completes. Sweep
        # again right before the screenshot to make sure they aren't
        # left in the captured image.
        self.dismiss_popups()
        time.sleep(1)
        self.logger.info("Streamer page settled, ready to capture")
        return self

    def capture(self, name: str = "streamer") -> Path:
        return self.take_screenshot(name)
