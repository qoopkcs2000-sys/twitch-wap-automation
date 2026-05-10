---
name: selenium-pytest-mobile-web
description: Use this skill when building or debugging a Selenium + pytest framework that drives a mobile web (WAP) site through Chrome's mobile emulator. Covers project structure, Chrome options that break on Chrome 127+, mobile emulation via deviceMetrics, recursive popup handling, resilient locator strategies, and the most common runtime errors. Trigger when the user mentions Twitch WAP, mobile emulator, Selenium mobile testing, "cannot parse capability: goog:chromeOptions", or asks for a mainstream Python automation framework structure.
---

# Selenium + pytest Mobile Web Automation

Lessons captured while building the Twitch WAP automation framework
(`F:\twich_test`). Apply this skill whenever you start, extend, or
troubleshoot a similar mobile-web Selenium project in Python.

## When to use

- Setting up a new Python automation framework for a mobile site
- Driving Chrome's mobile emulator with Selenium
- Debugging `cannot parse capability: goog:chromeOptions`
- Designing a Page Object Model that scales beyond a few flows
- Handling chained popups / overlays that hide the real UI
- Writing pytest fixtures that capture screenshots on failure

## Mainstream project layout

```
project_root/
├── README.md
├── requirements.txt
├── pytest.ini
├── conftest.py            # driver fixture + failure-screenshot hook
├── .gitignore
├── config/
│   └── settings.py        # env-driven configuration (URL, device, timeouts)
├── pages/                 # Page Object Model
│   ├── base_page.py       # waits, clicks, scrolls, screenshots
│   └── *_page.py          # one file per logical page
├── tests/
│   └── test_*.py
├── utils/
│   ├── driver_factory.py  # the only place that builds a browser
│   └── logger.py          # console + rotating-file logging
└── (runtime) screenshots/, reports/, logs/
```

Why each piece exists:

- `config/settings.py` reads every value from `os.getenv` with a
  default. Lets you flip device, headless, search query, timeouts via
  env vars in CI.
- `utils/driver_factory.py` is the single seam for browser changes
  (Firefox, Selenium Grid, BrowserStack later — one file change).
- `pages/base_page.py` wraps every wait/click/scroll/screenshot call
  so test code never imports `WebDriverWait` / `expected_conditions`.
- `conftest.py` exposes `driver` as a function-scoped fixture and
  installs a hook that screenshots failed tests automatically.

## Chrome options that break the test on Chrome 127+

These two `add_experimental_option` calls were valid for years and
silently became fatal on recent Chrome:

```python
# DO NOT USE on Chrome 127+
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
```

The chromedriver responds with:
```
selenium.common.exceptions.InvalidArgumentException:
Message: invalid argument: cannot parse capability: goog:chromeOptions
```

Remove both. Also drop `--disable-gpu` and
`--disable-blink-features=AutomationControlled` if the error persists
— they aren't required and have been the trigger on some builds.

## Mobile emulation: prefer CDP over the `mobileEmulation` capability

The legacy `add_experimental_option("mobileEmulation", ...)` shortcut
is convenient but it's a thin wrapper that doesn't fully propagate
`mobile=true` through Chrome's render path. Sites with mobile-vs-WAP
detection (Twitch, Reddit, etc.) frequently serve a half-broken
hybrid UI to a `mobileEmulation`-driven session — missing bottom
navigation, missing app banners, half the touch handlers.

The fix is to send the same CDP commands that DevTools' "Toggle
Device Toolbar" issues internally:

```python
driver.execute_cdp_cmd("Network.setUserAgentOverride", {
    "userAgent": ua,
    "acceptLanguage": "en-US,en;q=0.9",
    "platform": "Linux armv8l",
})
driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
    "width": 393, "height": 851,
    "deviceScaleFactor": 2.75,
    "mobile": True,                            # ← the critical flag
    "screenOrientation": {"type": "portraitPrimary", "angle": 0},
})
driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {
    "enabled": True, "maxTouchPoints": 5,
})
```

Apply these immediately after `webdriver.Chrome(...)` returns,
**before any `driver.get()`**. They take effect on the next
navigation. Don't combine with `mobileEmulation` capability — pick
one path.

If you need to verify visually, launch Chrome with
`--auto-open-devtools-for-tabs` so DevTools panel is open beside the
emulated viewport. Gate it on an env var (`OPEN_DEVTOOLS=true`) so
CI runs aren't slowed down.

## Driver management: Selenium Manager beats webdriver-manager on bleeding-edge Chrome

Selenium 4.6+ ships with Selenium Manager. Just do:

```python
driver = webdriver.Chrome(options=options)
```

No `Service`, no `ChromeDriverManager().install()`. Selenium Manager
finds (or downloads) a compatible driver every run. `webdriver-manager`
caches by Chrome major version and gets out of sync when Chrome
auto-updates between releases.

`webdriver-manager` can stay in `requirements.txt` for legacy code, but
the factory should not call it.

## Filter at Python level when locators fail

When the page object's CSS/XPath fallback list still misses (Twitch
likes to ship UI variants without `data-*` attributes), step outside
Selenium's locator API and filter elements in Python. For Twitch
search results, channel URLs are `twitch.tv/<single_segment>`, so:

```python
def _is_channel_link(self, element):
    href = element.get_attribute("href") or ""
    parsed = urlparse(href)
    if "twitch.tv" not in parsed.netloc:
        return False
    segments = [s for s in parsed.path.split("/") if s]
    return (
        len(segments) == 1
        and segments[0].lower() not in NON_CHANNEL_PATHS
    )

anchors = self.driver.find_elements(By.TAG_NAME, "a")
channels = [a for a in anchors if self._is_channel_link(a)]
```

This survives every UI rewrite that doesn't change channel URL shape.
Always de-dupe by `href` because mobile cards expose the same channel
through three anchors (image, avatar, title).

## Resilient locator strategy

Mobile UIs change often. Single-locator code is brittle. Use a list of
fallback locators and try each in order:

```python
SEARCH_ICON_LOCATORS = [
    (By.CSS_SELECTOR, "a[href='/search']"),
    (By.CSS_SELECTOR, "button[aria-label*='Search' i]"),
    (By.CSS_SELECTOR, "[data-a-target='search-button']"),
    (By.XPATH, "//a[contains(@href, '/search')]"),
]

for locator in SEARCH_ICON_LOCATORS:
    if self.is_visible(locator, timeout=3):
        self.click(locator, timeout=3)
        break
else:
    # Last-ditch: navigate directly
    self.driver.get(BASE_URL + "/search")
```

Log which locator matched. When the test fails six months later you'll
know which selector died.

## Recursive popup handling

Mobile sites chain overlays: cookie banner → mature-content gate → ad
close button → "open in app" sheet. One sweep is not enough. Recurse
with a depth cap so a single new permanent overlay can't loop forever.

```python
def dismiss_popups(self, max_depth: int = 3):
    if max_depth <= 0:
        return self
    dismissed_any = False
    for locator in POPUP_LOCATORS:
        if self._try_click(locator):
            dismissed_any = True
            time.sleep(1)  # let the next overlay render
    if dismissed_any:
        return self.dismiss_popups(max_depth - 1)
    return self
```

The "Open in App" prompt on Twitch mobile is a separate special case —
it only appears on first load and must be dismissed before any
navigation works. Treat it as a step inside `HomePage.load()`, not as a
generic popup.

## conftest.py: failure screenshot hook

Capture a PNG on every failed test without polluting test code:

```python
@pytest.fixture
def driver(request):
    drv = DriverFactory.create()
    yield drv
    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        drv.save_screenshot(f"screenshots/FAILED_{request.node.name}.png")
    drv.quit()

@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
```

The hook stores the result on the item; the fixture reads it during
teardown.

## pytest.ini essentials

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --html=reports/report.html --self-contained-html
log_cli = true
log_cli_level = INFO
markers =
    smoke: smoke tests
    wap: WAP / mobile flow tests
```

`--self-contained-html` makes the HTML report e-mailable as a single
file; `log_cli = true` means the page object's `self.logger.info(...)`
calls show up live during the run, which is invaluable when chasing a
flaky locator.

## Common runtime errors and the fix

| Symptom | Likely cause | Fix |
|---|---|---|
| `cannot parse capability: goog:chromeOptions` | Deprecated `useAutomationExtension` or `excludeSwitches` | Remove both options |
| Same error after that | `deviceName` shortcut not in chromedriver build | Use explicit `deviceMetrics` |
| `TimeoutException` finding search icon | Twitch shows "Open in App" overlay first | Dismiss overlay in `HomePage.load()` |
| `ElementClickInterceptedException` on streamer page | Cookie / mature-content gate | Run recursive `dismiss_popups()` |
| Driver downloaded but won't start | Chrome auto-updated past `webdriver-manager` cache | Drop to Selenium Manager |
| Empty results after `search_for` | Search input rendered as `type=text`, not `type=search` | Add fallback locator list |

## Quick checklist for a new mobile-web test project

1. Scaffold `config/`, `pages/`, `tests/`, `utils/`.
2. `Settings` class reads everything from env vars with defaults.
3. `DriverFactory.create()` uses Selenium Manager, no Service.
4. `mobileEmulation` set via `deviceMetrics` + `userAgent`.
5. `BasePage` exposes `find / find_visible / click / type_text /
   scroll_down / take_screenshot`.
6. Each page object owns its locator constants AND fallback variants.
7. `HomePage.load()` dismisses any first-load app prompt.
8. Last page in the flow has a recursive `dismiss_popups()`.
9. `conftest.py` provides the `driver` fixture and the failure
   screenshot hook.
10. `pytest.ini` enables HTML report, log_cli, and useful markers.

## Reference implementation

See `F:\twich_test`. Key files:
- `utils/driver_factory.py` — Chrome options + device profiles
- `pages/base_page.py` — shared element helpers
- `pages/home_page.py` — "Open in App" dismissal + fallback search icons
- `pages/streamer_page.py` — recursive popup handler
- `conftest.py` — driver fixture + failure screenshot hook
