"""Serve the local UI and continuously execute queued paper orders."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app import create_app
from app.models import db
from app.services.trading import process_all_open_orders
from app.services.weekly_report import is_weekly_email_due, run_weekly_email_if_due

POLL_SECONDS = max(5, int(os.environ.get("ALWAYS_ON_POLL_SECONDS", "30")))
EMAIL_RETRY_SECONDS = max(
    60, int(os.environ.get("WEEKLY_EMAIL_RETRY_SECONDS", "300"))
)
HOST = "127.0.0.1"
PORT = int(os.environ.get("APP_PORT", "5000"))
SINGLE_INSTANCE_PORT = 47653


def _configure_logging() -> logging.Logger:
    instance_dir = Path(__file__).resolve().parent / "instance"
    instance_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        instance_dir / "always_on.log",
        maxBytes=500_000,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger = logging.getLogger("always_on")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


def _acquire_single_instance() -> socket.socket:
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        lock.listen(1)
    except OSError:
        lock.close()
        raise RuntimeError("always_on.py is already running") from None
    return lock


def run_cycle(app) -> dict[str, int]:
    with app.app_context():
        try:
            return process_all_open_orders()
        finally:
            db.session.remove()


def _run_server(app, logger: logging.Logger) -> None:
    try:
        app.run(
            host=HOST,
            port=PORT,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
    except Exception:  # noqa: BLE001 — log failures from the server thread
        logger.exception("Local web server stopped unexpectedly")


def _run_weekly_email(app, logger: logging.Logger) -> None:
    try:
        email_status = run_weekly_email_if_due(app)
        if email_status:
            logger.info("%s", email_status)
    except Exception:  # noqa: BLE001 — email must not stop order polling
        logger.exception(
            "Weekly email failed; retrying in %s seconds",
            EMAIL_RETRY_SECONDS,
        )


def main() -> None:
    logger = _configure_logging()
    try:
        instance_lock = _acquire_single_instance()
    except RuntimeError as exc:
        logger.info("%s", exc)
        return

    app = create_app()
    server_thread = threading.Thread(
        target=_run_server,
        args=(app, logger),
        name="local-web-server",
        daemon=True,
    )
    server_thread.start()
    logger.info("Local web app available at http://%s:%s", HOST, PORT)
    logger.info("always_on started; polling every %s seconds", POLL_SECONDS)
    email_thread: threading.Thread | None = None
    last_email_attempt = float("-inf")
    try:
        while True:
            try:
                result = run_cycle(app)
                if result["filled"] or result["rejected"]:
                    logger.info(
                        "Processed %s account(s): %s filled, %s rejected",
                        result["accounts"],
                        result["filled"],
                        result["rejected"],
                    )
            except Exception:  # noqa: BLE001 — worker must survive transient failures
                logger.exception("Order-processing cycle failed")

            try:
                now = time.monotonic()
                email_idle = email_thread is None or not email_thread.is_alive()
                retry_ready = now - last_email_attempt >= EMAIL_RETRY_SECONDS
                if email_idle and retry_ready and is_weekly_email_due():
                    last_email_attempt = now
                    email_thread = threading.Thread(
                        target=_run_weekly_email,
                        args=(app, logger),
                        name="weekly-email",
                        daemon=True,
                    )
                    email_thread.start()
            except Exception:  # noqa: BLE001 — schedule checks must not stop polling
                logger.exception("Weekly email schedule check failed")

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        logger.info("always_on stopped")
    finally:
        instance_lock.close()


if __name__ == "__main__":
    main()
