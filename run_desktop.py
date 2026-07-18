"""Launch the investment tracker in a desktop window via pywebview."""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request

from app import create_app

HOST = "127.0.0.1"
PORT = 5000
URL = f"http://{HOST}:{PORT}"


def _run_flask(app):
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)


def _wait_for_server(timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL, timeout=1) as resp:
                if resp.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError("Flask server did not start in time")


def main() -> None:
    app = create_app()
    thread = threading.Thread(target=_run_flask, args=(app,), daemon=True)
    thread.start()
    _wait_for_server()

    try:
        import webview
    except ImportError as exc:
        raise SystemExit(
            "pywebview is required for the desktop shell. "
            "Install dependencies, or run: python wsgi.py"
        ) from exc

    webview.create_window(
        "Investment Tracker",
        URL,
        width=1180,
        height=800,
        min_size=(800, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
