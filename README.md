# Investment Tracker / Paper Trader

Personal local tracker for real holdings and paper accounts. Frontend built with Cursor, 
backend (services) handwritten with Claude/Cursor refinments (was the initial project).

Quotes via `yfinance`, UI `Flask`/`pywebview`, AI summary with `ollama` python library using gemma4:cloud.

Runtime settings use `config.toml` (gitignored) in at the repo root. If it does not exist,
the app uses `config.example.toml`, included in the shared repository, automatically. 



## Stack

- Flask + SQLite (SQLAlchemy)
- HTML / CSS / vanilla JS UI
- Chart.js for realized P&L
- Optional desktop shell via pywebview

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

The app runs with `config.example.toml` when `config.toml` is absent. To
customize settings, copy the example to `config.toml`, then edit host/port,
poll intervals, weekly email schedule, Ollama, cache TTLs, or desktop window
sizing. Restart `always_on.py` after changing config so the worker picks up
new values.

## Run in browser

```bash
python wsgi.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Run as desktop app

```bash
python run_desktop.py
```

Starts the local Flask server and opens a pywebview window on the same URL.

## Always-on local app

Run the local web app and order worker together:

```bash
python always_on.py
```

The browser UI is then available at
[http://127.0.0.1:5000](http://127.0.0.1:5000), and queued market and limit
orders continue processing while the UI is closed. The process checks open
orders on the interval in `config.toml` (`always_on_poll_seconds`, minimum 5),
allows only one instance, and writes activity/errors to
`instance/always_on.log`.

Change `host` / `port` in `config.toml` to use a different local bind address.
The defaults listen on `127.0.0.1` only, so the app is accessible from this
computer but not from other devices on the network.

### Start automatically on Windows

Open `shell:startup` from the Run dialog and create a shortcut with:

- **Target:** `<repo>\.venv\Scripts\pythonw.exe`
- **Arguments:** `<repo>\always_on.py`
- **Start in:** the repository directory

For this checkout, `<repo>` is
`C:\Users\nicco\Desktop\GitHub\investment-tracker-paper-trader`.

After signing in to Windows, open the configured URL in any browser. The
desktop launcher also reuses the already-running server instead of starting a
second copy.

### Weekly email digest

Weekly email is **off by default** (`weekly_email_enabled = false` in
`config.example.toml`) so a fresh install does not need Gmail or Ollama.
The UI and paper-order worker run normally either way.

To enable it, set in `config.toml`:

```toml
weekly_email_enabled = true
ollama_enabled = true   # optional; leave false to skip AI summary
```

Then restart `always_on`. While enabled, it sends a weekly email about **real**
accounts after 4:30 PM each Friday in the computer's local timezone. If the
computer is off or offline then, it sends the first time `always_on` is running
and email delivery succeeds afterward (including Saturday or later). The report
always covers the anchored **Friday-to-Friday** window (not a rolling
last-7-days from the send time). Metrics emphasize transaction-adjusted weekly
change, with all-time P&L kept separate. The email also includes holdings,
activity, market benchmarks (SPY/QQQ), possible news drivers, and (when
`ollama_enabled` is true) a short AI summary from local Ollama
(`gemma4:cloud` by default).

Before collecting the report or calling Ollama, the worker checks that email
settings resolve. Missing credentials fail fast, are logged, and are retried
later without stopping order polling.

In `config.toml`, the three email fields may be either an environment-variable
**name** (recommended) or a direct value:

```toml
email_sender = "GMAIL-INVESTMENT-UPDATE-EMAIL"
email_app_password = "GMAIL-INVESTMENT-UPDATE-APP-PW"
email_recipient = "PERSONAL-EMAIL"
```

Resolution is `os.getenv(config_value, config_value)`. With the defaults above,
set User environment variables so the Windows Startup shortcut inherits them:

```powershell
[System.Environment]::SetEnvironmentVariable("GMAIL-INVESTMENT-UPDATE-EMAIL", "your-bot@gmail.com", "User")
[System.Environment]::SetEnvironmentVariable("GMAIL-INVESTMENT-UPDATE-APP-PW", "your-app-password", "User")
[System.Environment]::SetEnvironmentVariable("PERSONAL-EMAIL", "you@example.com", "User")
```

Or put the addresses/password directly in `config.toml` (kept local because that
file is gitignored). Schedule, Ollama host/model, SMTP, lookback, and retry
timing are also controlled from `config.toml` — restart `always_on` after edits.

To force a test email immediately, ensure `weekly_email_enabled = true` and the
three email settings resolve, then run this from PowerShell in the repo root:

```powershell
@'
from app import create_app
from app.services.weekly_report import send_weekly_email

with create_app().app_context():
    print(send_weekly_email(mark_sent=False))
'@ | python -
```

This bypasses the weekly schedule and does not update the successful-send stamp,
so it will not suppress the next scheduled email. Set `ollama_enabled = false`
for a faster sender-only test without an AI summary.

A successful send writes `instance/last_weekly_email.txt` so the same weekly
report is not emailed twice after restarts. Failures are retried in the
background and logged to `instance/always_on.log`; they do not stop order
polling or the local web app.
If Ollama is enabled but unreachable, the email still sends with an
“AI summary unavailable” note.

## Account types

| Type | Behavior |
|------|----------|
| **Real** | Manual buy/sell with price, timestamp, and fees. No spendable cash balance. |
| **Paper** | Starting cash, market/limit orders filled against live quotes, deposits/withdrawals. |

## Data

SQLite database is stored at `instance/tracker.db` (gitignored).
