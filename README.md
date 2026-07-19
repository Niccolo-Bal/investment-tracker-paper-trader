# Investment Tracker / Paper Trader

Personal local tracker for real holdings and paper accounts with automated AI email updates.
Frontend built with Cursor, backend (app/services) handwritten with Claude/Cursor refinments.

Quotes via `yfinance`, UI `Flask`/`pywebview`, AI summary with `ollama` python library using gemma4:cloud by default.

Runtime settings use `config.toml` (gitignored) in at the repo root. If it does not exist,
the app uses `config.example.toml`, included in the shared repository, automatically. The app 
will run perfectly using the example config file, except for sending weekly emails (which 
requires emails and app passwords to be set up)


## Stack

- Flask + SQLite (SQLAlchemy)
- HTML / CSS / vanilla JS UI
- Chart.js for realized P&L
- Optional desktop shell via pywebview

## Setup

### Set up virtual environment

Windows:
```bash
python -m venv .venv
.venv\Scripts\activate
```

MacOS / Linux:
```bash
python -m venv .venv
source .venv/bin/activate
```

### Install dependencies
```bash
pip install -r requirements.txt
```

## Run in browser

```bash
python wsgi.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) or configured root + port.

## Run as desktop window

```bash
python run_desktop.py
```

Starts the local Flask server and opens a pywebview window on the same URL.

## Always-on local app

Run the local web app, automated emails, and order worker together:

```bash
python always_on.py
```

The browser UI is then available at [http://127.0.0.1:5000](http://127.0.0.1:5000) 
, queued market and limit orders continue processing while the UI 
is closed, and the email sender (if enabled) checks whether to send on startup and
again on fixed intervals. 

Change `host` / `port` in `config.toml` to use a different local bind address.
The defaults listen on `127.0.0.1` only.

### Start automatically on Windows

If you want the app open in the background consistently, it makes sense
to add it to startup.

Open `shell:startup` from the Run dialog and create a shortcut with: 

- **Target:** `"<repo>\.venv\Scripts\pythonw.exe" <repo>\always_on.py` 
- **Start in:** the repository directory

## Weekly email 

This is by far the most useful feature of the app.

Weekly email is **off by default** (`weekly_email_enabled = false` in
`config.example.toml`); the UI and paper-order worker run normally either way.

To enable it, set in `config.toml`:

```toml
weekly_email_enabled = true
ollama_enabled = true   # optional; leave false to skip AI summary
```

Then restart `always_on`. While enabled, it sends a weekly email about **real**
accounts after 4:30 PM each Friday in the computer's local timezone. If the
computer is off or offline then, it sends the first time `always_on` is running
and email delivery succeeds afterward (including Saturday or later). The email 
also includes holdings, activity, comparisons against market benchmarks (SPY/QQQ), 
possible news drivers, and (when `ollama_enabled` is true) a short AI summary, etc..

To set up the email, you need the sending Gmail account (must be gmail), an app password
and the receiving email address.

In `config.toml`, the three email fields may be either an environment-variable
name or a direct value:

```toml
email_sender = "MY-GMAIL-SENDER" # or "mysender@gmail.com"
email_app_password = "abcd efgh ijkl mnop" # Create through Security -> 2fA -> app passwords in Google account
email_recipient = "my.name@yahoo.com"
```

Remember to restart `always_on` after edits.

### Test email

Once everything is set up, you can force send an email by running this python script through
the following powershell command in the repo root:

```powershell
@'
from app import create_app
from app.services.weekly_report import send_weekly_email

with create_app().app_context():
    print(send_weekly_email(mark_sent=False))
'@ | python -
```

`send_weekly_email(mark_sent=False)` makes sure this doesn't suppress the next email update.


## Basic use

For the most part the UI is self-explanatory, but there are two big unobvious distinctions.

***Real accounts*** are for tracking real portfolio performance (presumably your own). Orders
are placed manually, with average price, timestamp, and volume being placed manually. This allows
the app to work without using your brokerages API, so you can plug in any portfolio you already have.

***Paper accounts*** are less of the purpose of the app but were a realatively easy additional 
implimentaion. Orders follow standard market/limit rules, with orderbooks running in the background 
as long as the app is on.

## Data

SQLite database is stored at `instance/tracker.db` (gitignored).
