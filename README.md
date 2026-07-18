# Investment Tracker / Paper Trader

Personal local tracker for real holdings and paper accounts. Quotes via `yfinance`.

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

## Account types

| Type | Behavior |
|------|----------|
| **Real** | Manual buy/sell with price, timestamp, and fees. No spendable cash balance. |
| **Paper** | Starting cash, market/limit orders filled against live quotes, deposits/withdrawals. |

## Data

SQLite database is stored at `instance/tracker.db` (gitignored).
