"""Diagnostic script: dump every anchor and button on twitch.tv.

Usage:
    python -m tools.inspect_twitch

It launches Chrome with the project's mobile emulation, opens
twitch.tv, dismisses the "Open in App" overlay if present, then prints
every <a> and <button> in the DOM along with the navigator values
that should confirm mobile emulation is active.

The script also writes ``twitch_dom.html`` and ``twitch_inspect.png``
to ``screenshots/`` so we can poke at the raw markup off-line.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Make the source/ tree importable when this is run as a standalone
# script (``python -m tools.inspect_twitch`` from inside source/, or
# direct execution). pytest doesn't need this — it picks the import
# path up from pytest.ini's ``pythonpath = source``.
SOURCE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOURCE_ROOT))

from selenium.webdriver.common.by import By  # noqa: E402

from config.settings import Settings  # noqa: E402
from pages.home_page import HomePage  # noqa: E402
from utils.driver_factory import DriverFactory  # noqa: E402


def banner(text: str) -> None:
    print()
    print("=" * 78)
    print(f"  {text}")
    print("=" * 78)


def main() -> int:
    Settings.ensure_dirs()
    driver = DriverFactory.create()
    try:
        # Load + dismiss "Open in App" overlay using the page object so
        # we exercise the same flow the tests do.
        HomePage(driver).load()

        # Give the SPA a few extra seconds to settle.
        time.sleep(3)

        banner("Navigator / viewport diagnostics")
        for expr in (
            "navigator.userAgent",
            "navigator.platform",
            "navigator.maxTouchPoints",
            "navigator.webdriver",
            "window.innerWidth",
            "window.innerHeight",
            "document.documentElement.clientWidth",
            "document.documentElement.clientHeight",
            "document.location.href",
        ):
            try:
                value = driver.execute_script(f"return {expr};")
            except Exception as exc:
                value = f"<error: {exc}>"
            print(f"{expr:40s} = {value}")

        banner("All <a> elements (href + visible text)")
        anchors = driver.find_elements(By.TAG_NAME, "a")
        for i, a in enumerate(anchors):
            try:
                href = (a.get_attribute("href") or "").strip()
                text = (a.text or "").strip().replace("\n", " ")[:60]
                aria = (a.get_attribute("aria-label") or "").strip()
                if not (href or text or aria):
                    continue
                print(f"[{i:03d}] href={href!s:55s} aria={aria!s:25s} text={text!r}")
            except Exception:
                continue

        banner("All <button> elements (aria-label + visible text)")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for i, b in enumerate(buttons):
            try:
                text = (b.text or "").strip().replace("\n", " ")[:60]
                aria = (b.get_attribute("aria-label") or "").strip()
                data_target = (b.get_attribute("data-a-target") or "").strip()
                if not (text or aria or data_target):
                    continue
                print(f"[{i:03d}] aria={aria!s:30s} data-a-target={data_target!s:30s} text={text!r}")
            except Exception:
                continue

        banner("Saving artefacts")
        page_path = Settings.SCREENSHOTS_DIR / "twitch_dom.html"
        shot_path = Settings.SCREENSHOTS_DIR / "twitch_inspect.png"
        page_path.write_text(driver.page_source, encoding="utf-8")
        driver.save_screenshot(str(shot_path))
        print(f"DOM saved   -> {page_path}")
        print(f"Shot saved  -> {shot_path}")

        # Hold the window open so the human can poke around DevTools.
        input("\nPress <Enter> to close the browser ...")
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
