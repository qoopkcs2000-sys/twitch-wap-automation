"""Project-wide pytest configuration.

Defines:
* the ``driver`` fixture that every test function receives
* a hook that captures a screenshot whenever a test fails
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from config.settings import Settings
from utils.driver_factory import DriverFactory
from utils.logger import get_logger
from utils.recorder import VideoRecorder

logger = get_logger("conftest")


def pytest_addoption(parser):
    """Add custom command line arguments."""
    parser.addoption(
        "--record",
        action="store_true",
        default=False,
        help="Record the test run as a GIF."
    )


@pytest.fixture(scope="function")
def driver(request):
    """Fresh browser per test for full isolation."""
    Settings.ensure_dirs()
    driver = DriverFactory.create()
    
    # Initialize recorder if flag is set
    recorder = None
    if request.config.getoption("--record"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = request.node.name
        record_path = Settings.RECORDINGS_DIR / f"{name}_{timestamp}.gif"
        recorder = VideoRecorder(driver, record_path)
        recorder.start()

    yield driver

    # Stop recording if active
    if recorder:
        recorder.stop()

    # Capture a screenshot on failure (the hook below sets ``rep_call``).
    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = request.node.name
            path = Settings.SCREENSHOTS_DIR / f"FAILED_{name}_{timestamp}.png"
            driver.save_screenshot(str(path))
            logger.error("Test failed - screenshot saved to %s", path)
        except Exception as exc:  # never let teardown raise
            logger.warning("Could not capture failure screenshot: %s", exc)

    driver.quit()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """Expose each phase result on the item so fixtures can read it."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
