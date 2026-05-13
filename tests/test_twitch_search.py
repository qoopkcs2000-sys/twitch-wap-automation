"""End-to-end test for the Twitch WAP search flow.

Steps:
    1. Go to Twitch
    2. Click the search icon
    3. Input "StarCraft II"
    4. Scroll down and search for a streamer
    5. Select one streamer
    6. Wait until the streamer page is loaded and take a screenshot
"""
from __future__ import annotations

import pytest

from config.settings import Settings
from pages.home_page import HomePage


@pytest.mark.wap
@pytest.mark.smoke
class TestTwitchSearch:
    """WAP search-and-watch smoke flow."""

    def test_search_starcraft_and_capture_streamer(self, driver):
        # Steps 1-2: home -> search
        search_page = HomePage(driver).load().open_search()

        # Step 3: search query
        search_page.search_for(Settings.SEARCH_QUERY)

        # Step 4-5: scroll down twice and select a streamer (recursive)
        streamer_page = search_page.find_streamer_recursively(index=0, max_retries=2)

        # Step 6: Wait for the streamer page to fully load and capture a screenshot.
        # Process:
        #   1. Dismiss any existing popups/overlays.
        #   2. Wait for video player and document readyState.
        #   3. Perform a final popup sweep for late-binding overlays.
        #   4. Capture the screenshot.
        screenshot_path = (
            streamer_page
            .dismiss_popups()       # initial sweep
            .wait_until_loaded()    # wait + final sweep inside
            .capture("starcraft_streamer")
        )

        # Sanity assertions on the output artifacts.
        assert screenshot_path.exists(), "Screenshot should be written to disk"
        assert screenshot_path.stat().st_size > 0, "Screenshot should not be empty"
        # And we should NOT have screenshotted a directory page.
        assert "/directory" not in driver.current_url, (
            f"Final URL is a directory page ({driver.current_url}); "
            "the test selected a category, not a streamer."
        )
