# twitch-wap-automation

Selenium + pytest framework for Twitch mobile web (WAP) automation.
Runs against the mobile site using Chrome's mobile emulation and CDP-based stealth.

## Test scenario

| Step | Description |
|------|-------------|
| 1 | Open Twitch |
| 2 | Tap the search icon |
| 3 | Type `StarCraft II` |
| 4 | Scroll the result list twice |
| 5 | Open the first streamer |
| 6 | Wait until the page is loaded, dismiss any pop-ups, take a screenshot |

## Project structure

```
twitch-wap-automation/
├── source/                      # production code (made importable via
│   │                              `pythonpath = source` in pytest.ini)
│   ├── config/
│   │   └── settings.py          # Environment-driven configuration
│   ├── pages/                   # Page Object Model
│   │   ├── base_page.py         # Shared waits / actions / screenshot helper
│   │   ├── home_page.py
│   │   ├── search_page.py
│   │   └── streamer_page.py     # Recursive popup dismisser lives here
│   ├── utils/
│   │   ├── driver_factory.py    # Builds Chrome with mobile emulation
│   │   ├── logger.py            # Console + rotating-file logging
│   │   └── recorder.py          # GIF Recording utility
│   └── tools/
│       └── inspect_twitch.py    # Standalone DOM diagnostic helper
├── tests/                       # pytest test cases
│   ├── conftest.py              # `driver` fixture + failure screenshot hook
│   └── test_twitch_search.py
├── recordings/                  # GIF recordings (from --record flag)
├── docs/                        # Static assets (demo.gif)
├── skills/                      # Framework-specific technical insights
│   └── selenium-pytest-mobile-web/
│       └── SKILL.md             # Lessons captured during development
├── pytest.ini
├── requirements.txt
└── README.md
```

### Why this layout

- **Page Object Model** isolates locators from test logic, so changes to
  Twitch's DOM ripple through one file instead of every test.
- **`config/settings.py`** centralises tuning knobs (URL, device, timeouts,
  query, scroll count). Every value can be overridden via environment
  variables, which makes the same code work locally and on CI.
- **`utils/driver_factory.py`** is the only place that knows how to build a
  browser. Switching to Firefox, a Selenium Grid, or BrowserStack later is
  a one-file change.
  with chained overlays (cookie banner → mature gate → ad close button)
  by sweeping all known dismissable elements and recursing while
  anything was clicked. This ensures a clean state before interaction.
- **Failure screenshots** are taken automatically by the conftest hook so
  CI runs always have visual evidence.
- **Resilient locators** use fallback lists to survive minor UI changes.

## Technical Highlights

### 1. Mobile Emulation via CDP
Instead of the legacy `mobileEmulation` capability, this framework uses **Chrome DevTools Protocol (CDP)** to set device metrics and user agents. This ensures the site treats the session as a true mobile device, preventing hybrid UI issues common in automation.

### 2. Recursive Popup Handling
Chained overlays (e.g., Cookie Banner -> Age Gate -> Ad) are handled via a recursive dismissal strategy with a depth cap. This ensures the UI is clear before interacting with the main content.

### 3. Resilient Locator Strategy
Page Objects use a list of fallback locators for critical elements. If the primary CSS selector fails, the framework automatically tries alternatives (ARIA labels, data attributes, XPaths) before falling back to direct navigation or throwing an error.

### 4. Automatic Failure Artifacts
The `conftest.py` hook automatically captures:
- **Screenshots**: Saved to `screenshots/FAILED_<test_name>.png`.
- **HTML Report**: Detailed execution logs and status.
- **GIF Recording**: Optional visual replay of the entire flow.

## Requirements

- Python 3.10+
- Google Chrome installed locally
- Internet access (Selenium 4.6+'s built-in Selenium Manager
  downloads a matching ChromeDriver on first run)

## Setup

```bash
# 1. Clone
git clone <your-repo-url>
cd twitch-wap-automation

# 2. Virtual environment (recommended)
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

## Running the tests

Run everything:

```bash
pytest
```

Run only the WAP smoke flow:

```bash
pytest -m wap
```

Run headlessly (useful for CI):

```bash
HEADLESS=true pytest
```

Override the search query / device without touching the code:

```bash
SEARCH_QUERY="League of Legends" MOBILE_DEVICE="iPhone 12 Pro" pytest

# Run and record a GIF of the execution
pytest -m wap --record
```

## Output artifacts

After a run you'll find:

- `reports/report.html` &mdash; pytest-html report (self-contained)
- `screenshots/` &mdash; per-test screenshots (incl. failure captures)
- `recordings/` &mdash; GIF recordings of the test execution (when `--record` is used)
- `logs/test_run.log` &mdash; rotating log file

## Demo

![Test run demo](docs/demo.gif)

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `cannot parse capability: goog:chromeOptions` | Deprecated Chrome options | Remove `useAutomationExtension` and `excludeSwitches` in `driver_factory.py`. |
| `TimeoutException` on search icon | "Open in App" overlay blocked the view | Handled in `HomePage.load()`; check if Twitch changed the overlay DOM. |
| `ElementClickInterceptedException` | Cookie banner or mature gate appeared | Ensure `dismiss_popups()` is called before the interaction. |
| Driver won't start after Chrome update | Cache mismatch in `webdriver-manager` | The framework uses Selenium Manager (v4.6+) which handles this automatically. |
| Empty search results | Twitch changed the input `type` | Check the fallback locators in `home_page.py`. |

## Extending the framework

| What you want to do | Where to change |
|---------------------|-----------------|
| Add a new page | New file in `source/pages/`, inherit `BasePage` |
| Add a new test | New `test_*.py` under `tests/` |
| Use a different browser | Extend `DriverFactory.create` |
| Run on a Selenium Grid | Add a `remote` branch in `DriverFactory` |
| Tune timeouts / device | Set env vars or edit `source/config/settings.py` |
| Handle a new popup | Append a locator to `StreamerPage.POPUP_LOCATORS` |
