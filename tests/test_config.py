"""Tests for config.toml loading and email setting resolution."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import config as config_mod
from app.config import ConfigError, load_config, resolve_email_setting


def _write_config(text: str) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".toml",
        delete=False,
    )
    with handle as fh:
        fh.write(text)
    return Path(handle.name)


class ConfigLoaderTests(unittest.TestCase):
    def test_loads_example_defaults(self):
        cfg = load_config(config_mod.EXAMPLE_CONFIG_PATH)
        self.assertEqual(cfg["host"], "127.0.0.1")
        self.assertEqual(cfg["port"], 5000)
        self.assertEqual(cfg["always_on_poll_seconds"], 30)
        self.assertEqual(cfg["benchmarks"], ["SPY", "QQQ"])
        self.assertEqual(cfg["email_sender"], "GMAIL-INVESTMENT-UPDATE-EMAIL")
        self.assertIsInstance(cfg["quote_cache_ttl_seconds"], float)
        self.assertFalse(cfg["weekly_email_enabled"])
        self.assertFalse(cfg["ollama_enabled"])

    def test_missing_config_raises(self):
        missing = Path(tempfile.gettempdir()) / "missing-config-does-not-exist.toml"
        if missing.exists():
            missing.unlink()
        with self.assertRaises(ConfigError):
            load_config(missing)

    def test_missing_default_config_uses_example(self):
        missing = Path(tempfile.gettempdir()) / "missing-default-config.toml"
        if missing.exists():
            missing.unlink()
        with patch.object(config_mod, "CONFIG_PATH", missing):
            cfg = load_config()
        self.assertEqual(cfg["host"], "127.0.0.1")
        self.assertEqual(cfg["port"], 5000)

    def test_invalid_port_raises(self):
        base = config_mod.EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8")
        path = _write_config(base.replace("port = 5000", "port = 99999"))
        self.addCleanup(path.unlink)
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_wrong_type_raises(self):
        base = config_mod.EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8")
        path = _write_config(
            base.replace("always_on_poll_seconds = 30", 'always_on_poll_seconds = "slow"')
        )
        self.addCleanup(path.unlink)
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_resolve_env_key(self):
        cfg = {
            "email_sender": "TEST_CFG_EMAIL_FROM",
            "email_app_password": "TEST_CFG_EMAIL_PW",
            "email_recipient": "TEST_CFG_EMAIL_TO",
        }
        os.environ["TEST_CFG_EMAIL_FROM"] = "bot@example.com"
        os.environ["TEST_CFG_EMAIL_PW"] = "secret-pw"
        os.environ["TEST_CFG_EMAIL_TO"] = "me@example.com"
        self.addCleanup(lambda: os.environ.pop("TEST_CFG_EMAIL_FROM", None))
        self.addCleanup(lambda: os.environ.pop("TEST_CFG_EMAIL_PW", None))
        self.addCleanup(lambda: os.environ.pop("TEST_CFG_EMAIL_TO", None))
        self.assertEqual(
            resolve_email_setting("email_sender", cfg), "bot@example.com"
        )
        self.assertEqual(
            resolve_email_setting("email_app_password", cfg), "secret-pw"
        )
        self.assertEqual(
            resolve_email_setting("email_recipient", cfg), "me@example.com"
        )

    def test_resolve_direct_value(self):
        cfg = {
            "email_sender": "direct-bot@example.com",
            "email_app_password": "direct-app-password",
            "email_recipient": "direct-me@example.com",
        }
        self.assertEqual(
            resolve_email_setting("email_sender", cfg), "direct-bot@example.com"
        )
        self.assertEqual(
            resolve_email_setting("email_app_password", cfg), "direct-app-password"
        )
        self.assertEqual(
            resolve_email_setting("email_recipient", cfg), "direct-me@example.com"
        )

    def test_missing_default_secret_env_raises(self):
        cfg = {
            "email_sender": "GMAIL-INVESTMENT-UPDATE-EMAIL",
            "email_app_password": "GMAIL-INVESTMENT-UPDATE-APP-PW",
            "email_recipient": "PERSONAL-EMAIL",
        }
        saved = {
            key: os.environ.pop(key, None)
            for key in (
                "GMAIL-INVESTMENT-UPDATE-EMAIL",
                "GMAIL-INVESTMENT-UPDATE-APP-PW",
                "PERSONAL-EMAIL",
            )
        }

        def _restore() -> None:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(_restore)
        with self.assertRaises(ConfigError):
            resolve_email_setting("email_sender", cfg)
        with self.assertRaises(ConfigError):
            resolve_email_setting("email_app_password", cfg)
        with self.assertRaises(ConfigError):
            resolve_email_setting("email_recipient", cfg)


if __name__ == "__main__":
    unittest.main()
