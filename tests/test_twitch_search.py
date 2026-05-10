"""End-to-end test for the Twitch WAP search flow.

Steps (per the assignment brief):
    1. go to Twitch
    2. click the search icon
    3. input "StarCraft II"
    4. scroll down 2 times
    5. select one streamer
    6. wait until the streamer page is loaded and take a screenshot
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

        # Step 4: scroll down twice
        search_page.scroll_results(times=Settings.SCROLL_TIMES)

        # Step 5: open the first streamer in the result list
        streamer_page = search_page.open_streamer(index=0)

        # Step 6: per the assignment ("on the streamer page wait
        # until all is load and take a screenshot") we:
        #   1. dismiss any popup that's already up before we wait,
        #   2. wait until the page is fully loaded — wait_until_loaded
        #      itself runs another popup sweep at the end so the
        #      capture is clean,
        #   3. capture the screenshot.
        screenshot_path = (
            streamer_page
            .dismiss_popups()       # initial sweep
            .wait_until_loaded()    # wait + final sweep inside
            .capture("starcraft_streamer")
        )

        # Sanity assertions on the deliverable.
        assert screenshot_path.exists(), "Screenshot should be written to disk"
        assert screenshot_path.stat().st_size > 0, "Screenshot should not be empty"
        # And we should NOT have screenshotted a directory page.
        assert "/directory" not in driver.current_url, (
            f"Final URL is a directory page ({driver.current_url}); "
            "the test selected a category, not a streamer."
        )
