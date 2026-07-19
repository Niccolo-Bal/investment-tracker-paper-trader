"""Launch the investment tracker in a desktop window via pywebview."""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request

from app import create_app
from app.config import CONFIG

HOST = CONFIG["host"]
PORT = CONFIG["port"]
URL = f"http://{HOST}:{PORT}"


def _run_flask(app):
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)


def _wait_for_server(
    timeout: float = CONFIG["desktop_startup_timeout_seconds"],
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                URL, timeout=CONFIG["desktop_request_timeout_seconds"]
            ) as resp:
                if resp.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError("Flask server did not start in time")


def _server_is_running() -> bool:
    try:
        with urllib.request.urlopen(
            URL, timeout=CONFIG["desktop_request_timeout_seconds"]
        ) as resp:
            return resp.status < 500
    except (urllib.error.URLError, TimeoutError):
        return False


def main() -> None:
    if not _server_is_running():
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
        width=CONFIG["desktop_window_width"],
        height=CONFIG["desktop_window_height"],
        min_size=(CONFIG["desktop_min_width"], CONFIG["desktop_min_height"]),
    )
    webview.start()


if __name__ == "__main__":
    main()
