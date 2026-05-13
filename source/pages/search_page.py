"""Twitch mobile search page."""
from __future__ import annotations

import time
from urllib.parse import quote_plus, urlparse

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement

from config.settings import Settings
from pages.base_page import BasePage


class SearchPage(BasePage):
    """Search input + result grid."""

    # ------------------------------------------------------------------
    # Locator fallbacks for the search input.
    # ------------------------------------------------------------------
    SEARCH_INPUT_LOCATORS = [
        (By.CSS_SELECTOR, "input[type='search']"),
        (By.CSS_SELECTOR, "input[aria-label*='Search' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='Search' i]"),
        (By.CSS_SELECTOR, "[data-a-target='tw-input']"),
        (By.CSS_SELECTOR, "input"),
    ]

    # Twitch channel paths look like ``/<channel_name>`` — a single path
    # segment. Anything in this set is *not* a channel even though it
    # also matches the single-segment pattern.
    NON_CHANNEL_PATHS = {
        "search", "directory", "login", "signup", "p",
        "downloads", "jobs", "about", "settings",
        "wallet", "drops", "subscriptions", "friends",
        # Bottom-nav destinations that pass the single-segment test.
        "notifications", "inbox", "messages", "whispers",
        "activity", "videos", "following", "popout",
        "turbo", "prime", "store", "broadcast",
        # m.twitch.tv specific
        "home", "discover", "feed", "recommended",
        "browse", "live", "channels", "esports",
    }

    # JS that walks an element's ancestors and returns true if any of
    # them is a structural nav/footer container. Used to filter out
    # bottom-nav anchors that would otherwise pass the channel test.
    #
    # IMPORTANT: ``header``/``footer`` are intentionally excluded from
    # the class-name regex because Twitch's BEM naming sprinkles them
    # into legitimate content sections (``search-results__header``,
    # ``section-header``...). We only treat them as signals when they
    # appear as actual HTML tags or ARIA roles, not as substrings of
    # class names. The class-name fallback covers tab/nav bars only.
    _IS_IN_NAV_OR_FOOTER_JS = """
    let el = arguments[0];
    while (el) {
        if (!el.tagName) { el = el.parentElement; continue; }
        const tag = el.tagName.toUpperCase();
        if (tag === 'NAV' || tag === 'FOOTER' || tag === 'HEADER') return true;
        const role = el.getAttribute && el.getAttribute('role');
        if (role === 'navigation' || role === 'banner' || role === 'contentinfo' ||
            role === 'tablist' || role === 'menubar') return true;
        const cls = (el.className || '').toString().toLowerCase();
        const id  = (el.id || '').toString().toLowerCase();
        if (/(^|[\\s_-])(navbar|tabbar|tab-bar|bottom-bar|bottom-nav|app-bar)([\\s_-]|$)/.test(cls) ||
            /(navbar|tabbar|tab-bar|bottom-bar|bottom-nav|app-bar)/.test(id))
            return true;
        el = el.parentElement;
    }
    return false;
    """

    # ------------------------------------------------------------------
    def _find_search_input(self) -> WebElement:
        for locator in self.SEARCH_INPUT_LOCATORS:
            if self.is_visible(locator, timeout=3):
                self.logger.info("Search input found via %s", locator)
                return self.find_visible(locator, timeout=3)
        raise TimeoutException("Could not locate the search input field")

    # ------------------------------------------------------------------
    # Locators for elements that, when clicked, commit the typed query
    # and navigate to the full search results page. We try them in
    # order. Twitch's autocomplete dropdown usually exposes a
    # "Search for X" entry — that's the canonical commit affordance.
    SEARCH_COMMIT_LOCATORS = [
        # Explicit "Search for ..." suggestion (most reliable)
        (By.XPATH, "//a[starts-with(normalize-space(.), 'Search for')]"),
        (By.XPATH, "//button[starts-with(normalize-space(.), 'Search for')]"),
        (By.XPATH, "//*[@role='option'][starts-with(normalize-space(.), 'Search for')]"),
        # First option in autocomplete listbox
        (By.CSS_SELECTOR, "[role='listbox'] [role='option']"),
        (By.CSS_SELECTOR, "[data-a-target='search-suggestion-1']"),
        # Submit button next to input (rare on mobile)
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "button[aria-label*='Search' i]"),
    ]

    def search_for(self, query: str) -> "SearchPage":
        """Strictly perform "input <query>" (assignment step 3).

        Types the query into the search field and commits it via UI
        only — no ``driver.get`` shortcut. The commit attempt order:
            1. Press Enter (works on the dedicated /search page)
            2. ``element.submit()`` (W3C form submit)
            3. Click an autocomplete suggestion (mobile)
        We never silently navigate behind the user's back; if every
        commit path fails we raise so the test reports honestly.
        """
        self.logger.info("Searching for: %s", query)
        element = self._find_search_input()
        element.clear()
        element.send_keys(query)

        # Attempt 1: Enter key
        element.send_keys(Keys.ENTER)
        time.sleep(2)
        if self._results_loaded():
            self._wait_for_results()
            return self
        self.logger.info("Enter did not navigate; trying form submit")

        # Attempt 2: HTML form submit (if the input lives in a <form>)
        try:
            element.submit()
            time.sleep(2)
            if self._results_loaded():
                self._wait_for_results()
                return self
        except Exception as exc:
            self.logger.info("element.submit() not applicable: %s", exc.__class__.__name__)

        # Attempt 3: click an autocomplete suggestion
        self.logger.info("Looking for an autocomplete commit element")
        for locator in self.SEARCH_COMMIT_LOCATORS:
            if not self.is_visible(locator, timeout=3):
                continue
            try:
                self.click(locator, timeout=3)
                self.logger.info("Search committed via %s", locator)
                time.sleep(2)
                if self._results_loaded():
                    self._wait_for_results()
                    return self
            except Exception as exc:
                self.logger.warning("Failed to click %s: %s", locator, exc)

        raise AssertionError(
            f"Search query '{query}' was typed but no commit action "
            f"navigated to a results page. Current URL: "
            f"{self.driver.current_url}"
        )

    def _results_loaded(self) -> bool:
        """True if the current URL looks like a search results page."""
        url = self.driver.current_url.lower()
        return "/search" in url or "search?" in url or "term=" in url

    # ------------------------------------------------------------------
    # JS that finds clickable elements whose text contains a live-stream
    # "X viewers" / "X.YK viewers" pattern. Returns the nearest
    # clickable ancestor (anchor / button / role-button / role-link)
    # so a Selenium ``.click()`` on the returned element actually
    # navigates. Used as a fallback when streamer cards on the page
    # are React buttons without exposed href/data-href.
    _STREAMER_CARDS_BY_TEXT_JS = r"""
    // m.twitch.tv ships streamer cards as plain <div> with React
    // onClick handlers — no <a>, no <button>, no ARIA role.
    //
    // Strategy:
    //   1. Find the DEEPEST element containing "X viewers" text
    //      (so we don't match an enclosing section by accident).
    //   2. Walk UP from that element to the nearest clickable
    //      ancestor (anchor/button/role/cursor:pointer).
    //   3. Reject if the clickable's textContent contains
    //      "Followers" — that pattern is on category meta cards
    //      (e.g. "385 Viewers · 2.6M Followers"), not on streams.
    //
    // The Followers filter is what keeps us from accidentally
    // selecting the StarCraft II category card on a category page
    // and ending up on the wrong destination.

    function isClickable(el) {
        if (!el || !el.tagName) return false;
        const tag = el.tagName.toUpperCase();
        if (tag === 'A' || tag === 'BUTTON') return true;
        const role = el.getAttribute && el.getAttribute('role');
        if (role === 'button' || role === 'link') return true;
        try {
            return window.getComputedStyle(el).cursor === 'pointer';
        } catch (_) {
            return false;
        }
    }

    function nearestClickable(el) {
        while (el) {
            if (isClickable(el)) return el;
            el = el.parentElement;
        }
        return null;
    }

    const VIEWER_RX = /\b\d+(\.\d+)?\s*[KkMm]?\s+(viewer|viewers|觀眾|观众)\b/i;
    const FOLLOWERS_RX = /\bfollowers?\b/i;

    const result = [];
    const seen = new Set();

    document.querySelectorAll('*').forEach(el => {
        if (!el.tagName) return;
        const tag = el.tagName.toUpperCase();
        if (['BODY','HTML','SCRIPT','STYLE','NOSCRIPT','IMG','SVG'].includes(tag))
            return;

        const text = (el.textContent || '').trim();
        if (!VIEWER_RX.test(text)) return;

        // Keep only the deepest element with the viewer text — if
        // any child also matches, defer to that child's iteration.
        for (const child of el.children) {
            if (VIEWER_RX.test((child.textContent || '').trim())) return;
        }

        const clickable = nearestClickable(el);
        if (!clickable) return;

        // Skip category meta cards (they have "Followers" in text).
        if (FOLLOWERS_RX.test(clickable.textContent || '')) return;

        if (seen.has(clickable)) return;
        seen.add(clickable);
        result.push(clickable);
    });

    return result;
    """

    def _collect_cards_by_viewer_text(self) -> list[WebElement]:
        """Locate streamer cards by their viewer-count text + clickable
        ancestor. Works for m.twitch.tv where cards are <button>s
        without href."""
        try:
            cards = self.driver.execute_script(self._STREAMER_CARDS_BY_TEXT_JS) or []
        except Exception as exc:
            self.logger.warning("viewer-text scan failed: %s", exc)
            return []
        if cards:
            sample = self.driver.execute_script(
                "return arguments[0].slice(0, 3).map(el => "
                "({tag: el.tagName, cls: el.className||'', "
                "txt: (el.textContent||'').slice(0,80)}));",
                cards,
            )
            self.logger.info("viewer-text scan found %d card(s); sample=%s", len(cards), sample)
        return cards

    def _is_channel_link(self, element: WebElement) -> bool:
        """Decide whether an <a> element points at a Twitch channel.
        
        Strictly excludes categories, directories, and other internal paths.
        """
        href = element.get_attribute("href") or ""
        if not href:
            return False
            
        parsed = urlparse(href)
        # Twitch channels live on twitch.tv, not on m.twitch.tv subpaths.
        if parsed.netloc and "twitch.tv" not in parsed.netloc:
            return False
            
        # STRATEGY: Exclude anything containing '/directory' — these are 
        # categories (e.g., /directory/category/starcraft-ii) not streamers.
        path = parsed.path.lower()
        if "/directory" in path:
            return False

        # Strip leading/trailing slashes and split.
        segments = [s for s in path.split("/") if s]
        if len(segments) != 1:
            return False
            
        return segments[0] not in self.NON_CHANNEL_PATHS

    def _is_in_nav(self, element: WebElement) -> bool:
        """True if the element sits inside a structural nav/footer/header."""
        try:
            return bool(
                self.driver.execute_script(self._IS_IN_NAV_OR_FOOTER_JS, element)
            )
        except Exception:
            return False

    def _collect_channel_links(self) -> list[WebElement]:
        """Return every clickable element that looks like a streamer card.

        Two-tier strategy:
          1. Walk every <a>/<button>/role-link/role-button and treat
             elements whose href points to ``/<channel>`` as cards.
          2. If tier 1 returns nothing (m.twitch.tv ships React
             buttons without href), fall back to "find any element
             whose text matches an 'X viewers' line and walk up to the
             nearest clickable ancestor".

        Tier 1 is preferred because we can verify the target URL up
        front; tier 2 is the only way to grab href-less mobile cards.
        """
        # ----- Tier 1: anchor-based detection -----
        candidate_sel = "a, [role='link'], [role='button'], button, [data-href], [data-test-href]"
        anchors = self.driver.find_elements(By.CSS_SELECTOR, candidate_sel)
        channels: list[WebElement] = []
        seen_hrefs: set[str] = set()

        stats = {
            "no_href": 0,
            "external": 0,
            "multi_segment": 0,
            "blacklist": 0,
            "in_nav": 0,
            "duplicate": 0,
        }
        sample_rejected: list[str] = []
        sample_in_nav: list[str] = []

        for anchor in anchors:
            try:
                href = (
                    anchor.get_attribute("href")
                    or anchor.get_attribute("data-href")
                    or anchor.get_attribute("data-test-href")
                    or ""
                )
                if not href:
                    stats["no_href"] += 1
                    continue

                parsed = urlparse(href)
                # Some hrefs are relative ("/wardiii"); urlparse treats
                # them as having no netloc. Treat that as "this domain".
                if parsed.netloc and "twitch.tv" not in parsed.netloc:
                    stats["external"] += 1
                    continue

                segments = [s for s in parsed.path.split("/") if s]
                if len(segments) != 1:
                    stats["multi_segment"] += 1
                    if len(sample_rejected) < 5:
                        sample_rejected.append(href)
                    continue

                if segments[0].lower() in self.NON_CHANNEL_PATHS:
                    stats["blacklist"] += 1
                    continue

                if self._is_in_nav(anchor):
                    stats["in_nav"] += 1
                    if len(sample_in_nav) < 5:
                        sample_in_nav.append(href)
                    continue

                if href in seen_hrefs:
                    stats["duplicate"] += 1
                    continue
                seen_hrefs.add(href)
                channels.append(anchor)
            except Exception:
                # Stale element on a re-render — just skip.
                continue

        self.logger.debug(
            "Anchor scan: total=%d kept=%d rejected=%s",
            len(anchors), len(channels), stats,
        )
        if channels:
            return channels

        # ----- Tier 2: text-based card detection -----
        text_cards = self._collect_cards_by_viewer_text()
        if text_cards:
            self.logger.info(
                "Found %d streamer card(s) via viewer-text scan", len(text_cards),
            )
            return text_cards

        self.logger.warning(
            "No channel links kept on %s. Total candidates=%d, rejects=%s. "
            "Sample multi-segment hrefs=%s. Sample in-nav hrefs=%s. "
            "Viewer-text scan also returned 0.",
            self.driver.current_url, len(anchors), stats,
            sample_rejected, sample_in_nav,
        )
        return []

    def _wait_for_results(self) -> None:
        """Poll until at least one channel link is present in the DOM."""
        deadline = time.monotonic() + Settings.DEFAULT_TIMEOUT
        # Suppress repeat WARNINGs from the polling loop — only log
        # the first reject snapshot, then stay silent until we either
        # find results or time out.
        original_warning = self.logger.warning
        warned = {"emitted": False}

        def quiet_warning(*args, **kwargs):
            if not warned["emitted"]:
                warned["emitted"] = True
                original_warning(*args, **kwargs)

        self.logger.warning = quiet_warning  # type: ignore[assignment]
        try:
            while time.monotonic() < deadline:
                if self._collect_channel_links():
                    return
                time.sleep(0.5)
        finally:
            self.logger.warning = original_warning  # type: ignore[assignment]
        raise TimeoutException("No streamer cards rendered after search")

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    def scroll_results(self, times: int = 2) -> "SearchPage":
        self.logger.info("Scrolling result list %d time(s)", times)
        self.scroll_down(times=times, pause=1.5)
        return self

    def find_streamer_recursively(self, index: int = 0, max_retries: int = 3) -> "StreamerPage":
        """Locate and click a streamer using a recursive search-and-scroll strategy.
        
        If not enough streamer cards are found in the current view, it scrolls 
        down and recurses. This satisfies the 'Recursivity' objective in a core 
        functional way.
        """
        cards = self._collect_channel_links()
        
        # Base case: we found the streamer at the requested index
        if len(cards) > index:
            target = cards[index]
            self.logger.info("Streamer found at index %d, selecting...", index)
            return self._click_streamer(target)
            
        # Recursive case: not enough cards, scroll and try again
        if max_retries > 0:
            self.logger.info(
                "Not enough streamers found (%d/%d). Scrolling and recursing (retries left: %d)",
                len(cards), index + 1, max_retries
            )
            self.scroll_down(times=1, pause=1.5)
            return self.find_streamer_recursively(index, max_retries - 1)
            
        # Failure case: ran out of retries
        raise AssertionError(
            f"Could not find enough streamer cards after recursive scrolling. "
            f"Found: {len(cards)}, Target index: {index}"
        )

    def _click_streamer(self, target: WebElement) -> "StreamerPage":
        """Helper to handle the click and navigation logic."""
        href = target.get_attribute("href")
        self.logger.info("Selecting streamer -> %s", href)
        
        before_url = self.driver.current_url
        try:
            target.click()
        except Exception as exc:
            self.logger.warning(
                "Native click failed (%s); retrying via JS click",
                exc.__class__.__name__,
            )
            self.driver.execute_script("arguments[0].click();", target)

        time.sleep(2)
        after_url = self.driver.current_url
        self.logger.info("After click URL: %s", after_url)
        
        if "/directory" in after_url or after_url == before_url:
            self.logger.warning(
                "Click did not navigate to a streamer page (still on %s)",
                after_url,
            )

        from pages.streamer_page import StreamerPage
        return StreamerPage(self.driver)

    # ------------------------------------------------------------------
    def open_streamer(self, index: int = 0) -> "StreamerPage":
        """Legacy method for compatibility, delegates to recursive search."""
        return self.find_streamer_recursively(index=index, max_retries=2)
