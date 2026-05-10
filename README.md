# twitch-wap-automation

Selenium + pytest framework for the **Home Test - AQA** assignment.
Runs against Twitch's mobile web (WAP) using Chrome's mobile emulator.

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
twich_test/
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
│   │   └── logger.py            # Console + rotating-file logging
│   └── tools/
│       └── inspect_twitch.py    # Standalone DOM diagnostic helper
├── tests/                       # pytest test cases
│   ├── conftest.py              # `driver` fixture + failure screenshot hook
│   └── test_twitch_search.py
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
- **Recursive popup handling** in `StreamerPage.dismiss_popups` deals
  with chained overlays (cookie banner → mature gate → ad close button)
  by sweeping all known dismissable elements and recursing while
  anything was clicked. This satisfies the *Recursivity* requirement.
- **Failure screenshots** are taken automatically by the conftest hook so
  CI runs always have visual evidence.

## Requirements

- Python 3.10+
- Google Chrome installed locally
- Internet access (Selenium 4.6+'s built-in Selenium Manager
  downloads a matching ChromeDriver on first run)

## Setup

```bash
# 1. Clone
git clone <your-repo-url>
cd twich_test

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
```

## Output artifacts

After a run you'll find:

- `reports/report.html` &mdash; pytest-html report (self-contained)
- `screenshots/` &mdash; per-test screenshots (incl. failure captures)
- `logs/test_run.log` &mdash; rotating log file

## Demo

![Test run demo](docs/demo.gif)

> Replace `docs/demo.gif` with a recorded run before submitting.

## Extending the framework

| What you want to do | Where to change |
|---------------------|-----------------|
| Add a new page | New file in `source/pages/`, inherit `BasePage` |
| Add a new test | New `test_*.py` under `tests/` |
| Use a different browser | Extend `DriverFactory.create` |
| Run on a Selenium Grid | Add a `remote` branch in `DriverFactory` |
| Tune timeouts / device | Set env vars or edit `source/config/settings.py` |
| Handle a new popup | Append a locator to `StreamerPage.POPUP_LOCATORS` |
