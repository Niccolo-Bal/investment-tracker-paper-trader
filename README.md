# Investment Tracker / Paper Trader

Personal local tracker for real holdings and paper accounts. Frontend built with Cursor, 
backend (services) handwritten with Claude/Cursor refinments (was the initial project).

Quotes via `yfinance`, UI `Flask`/`pywebview`, AI summary with `ollama` python library using gemma4:cloud.

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
orders every 30 seconds, allows only one instance, and writes activity/errors
to `instance/always_on.log`.

Set `APP_PORT` to use a different local port, or `ALWAYS_ON_POLL_SECONDS` to
change the order interval (minimum 5 seconds). For example, in PowerShell:

```powershell
$env:APP_PORT = "5050"
python always_on.py
```

To keep that port after signing out or restarting Windows, run
`setx APP_PORT 5050` once before creating or using the startup shortcut.

The server only listens on `127.0.0.1`, so it is accessible from this computer
but not from other devices on the network.

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

While `always_on` is running, it sends a weekly email about **real** accounts
after 4:30 PM each Friday in the computer's local timezone. If the computer is
off or offline then, it sends the first time `always_on` is running and email
delivery succeeds afterward (including Saturday or later). The report always
covers the anchored **Friday-to-Friday** window (not a rolling last-7-days from
the send time). Metrics emphasize transaction-adjusted weekly change, with
all-time P&L kept separate. The email also includes holdings, activity, market
benchmarks (SPY/QQQ), possible news drivers, and a short AI summary from local
Ollama (`gemma4:cloud` by default).

Set these as **User** environment variables so the Startup shortcut inherits
them (PowerShell examples):

```powershell
[System.Environment]::SetEnvironmentVariable("GMAIL-INVESTMENT-UPDATE-EMAIL", "your-bot@gmail.com", "User")
[System.Environment]::SetEnvironmentVariable("GMAIL-INVESTMENT-UPDATE-APP-PW", "your-app-password", "User")
[System.Environment]::SetEnvironmentVariable("PERSONAL-EMAIL", "you@example.com", "User")
```

Optional overrides:

| Variable | Default | Meaning |
|----------|---------|---------|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama HTTP API |
| `OLLAMA_MODEL` | `gemma4:cloud` | Model name |
| `WEEKLY_EMAIL_LOOKBACK_DAYS` | `7` | Activity window |
| `WEEKLY_EMAIL_WEEKDAY` | `4` (Friday) | Python `date.weekday()` |
| `WEEKLY_EMAIL_HOUR` | `16` | Local-time send hour |
| `WEEKLY_EMAIL_MINUTE` | `30` | Local-time send minute |
| `WEEKLY_EMAIL_RETRY_SECONDS` | `300` | Delay after a failed send |

A successful send writes `instance/last_weekly_email.txt` so the same weekly
report is not emailed twice after restarts. Failures are retried in the
background and logged to `instance/always_on.log`; they do not stop order
polling or the local web app.
Ollama must be reachable when the digest runs; if it is down, the email still
sends with an “AI summary unavailable” note.

## Account types

| Type | Behavior |
|------|----------|
| **Real** | Manual buy/sell with price, timestamp, and fees. No spendable cash balance. |
| **Paper** | Starting cash, market/limit orders filled against live quotes, deposits/withdrawals. |

## Data

SQLite database is stored at `instance/tracker.db` (gitignored).
