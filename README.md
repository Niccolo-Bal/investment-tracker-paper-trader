# Meridian Ledger

Local investment tracker and paper trader. Track real holdings with manual cost basis, or practice with virtual cash, market/limit orders, and a full ledger — priced with Yahoo Finance via `yfinance`.

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

## Account types

| Type | Behavior |
|------|----------|
| **Real** | Manual buy/sell with price, timestamp, and fees. No spendable cash; optional reference cash for P&L context. |
| **Paper** | Starting cash, market/limit orders filled against live quotes, deposits/withdrawals. |

## Data

SQLite database is stored at `instance/tracker.db` (gitignored).
