"""Load and validate root config.toml for runtime settings."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.toml"
EXAMPLE_CONFIG_PATH = ROOT_DIR / "config.example.toml"

EMAIL_SETTING_KEYS = ("email_sender", "email_app_password", "email_recipient")
KNOWN_EMAIL_ENV_KEYS = frozenset(
    {
        "GMAIL-INVESTMENT-UPDATE-EMAIL",
        "GMAIL-INVESTMENT-UPDATE-APP-PW",
        "PERSONAL-EMAIL",
    }
)

_REQUIRED: dict[str, type | tuple[type, ...]] = {
    "host": str,
    "port": int,
    "always_on_poll_seconds": int,
    "single_instance_port": int,
    "weekly_email_retry_seconds": int,
    "database_filename": str,
    "always_on_log_filename": str,
    "weekly_email_stamp_filename": str,
    "log_max_bytes": int,
    "log_backup_count": int,
    "secret_key": str,
    "templates_auto_reload": bool,
    "desktop_startup_timeout_seconds": (int, float),
    "desktop_request_timeout_seconds": (int, float),
    "desktop_window_width": int,
    "desktop_window_height": int,
    "desktop_min_width": int,
    "desktop_min_height": int,
    "quote_cache_ttl_seconds": (int, float),
    "history_cache_ttl_seconds": (int, float),
    "enrichment_cache_ttl_seconds": (int, float),
    "history_bar_cache_ttl_seconds": (int, float),
    "benchmarks": list,
    "weekly_email_enabled": bool,
    "ollama_enabled": bool,
    "weekly_email_lookback_days": int,
    "weekly_email_weekday": int,
    "weekly_email_hour": int,
    "weekly_email_minute": int,
    "ollama_host": str,
    "ollama_model": str,
    "ollama_timeout_seconds": (int, float),
    "smtp_host": str,
    "smtp_port": int,
    "smtp_timeout_seconds": (int, float),
    "email_sender": str,
    "email_app_password": str,
    "email_recipient": str,
}


class ConfigError(RuntimeError):
    """Invalid or missing configuration."""


def _validate(raw: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in _REQUIRED if key not in raw]
    if missing:
        raise ConfigError(f"Missing config key(s): {', '.join(missing)}")

    cfg: dict[str, Any] = {}
    for key, expected in _REQUIRED.items():
        value = raw[key]
        if not isinstance(value, expected):
            type_name = (
                " | ".join(t.__name__ for t in expected)
                if isinstance(expected, tuple)
                else expected.__name__
            )
            raise ConfigError(
                f"Config '{key}' must be {type_name}, got {type(value).__name__}"
            )
        cfg[key] = value

    if not cfg["host"].strip():
        raise ConfigError("Config 'host' must be non-empty")
    if not (1 <= cfg["port"] <= 65535):
        raise ConfigError("Config 'port' must be between 1 and 65535")
    if not (1 <= cfg["single_instance_port"] <= 65535):
        raise ConfigError("Config 'single_instance_port' must be between 1 and 65535")
    if cfg["always_on_poll_seconds"] < 5:
        raise ConfigError("Config 'always_on_poll_seconds' must be >= 5")
    if cfg["weekly_email_retry_seconds"] < 60:
        raise ConfigError("Config 'weekly_email_retry_seconds' must be >= 60")
    if cfg["log_max_bytes"] < 1_000:
        raise ConfigError("Config 'log_max_bytes' must be >= 1000")
    if cfg["log_backup_count"] < 0:
        raise ConfigError("Config 'log_backup_count' must be >= 0")
    if cfg["weekly_email_lookback_days"] < 1:
        raise ConfigError("Config 'weekly_email_lookback_days' must be >= 1")
    if not (0 <= cfg["weekly_email_weekday"] <= 6):
        raise ConfigError("Config 'weekly_email_weekday' must be 0..6")
    if not (0 <= cfg["weekly_email_hour"] <= 23):
        raise ConfigError("Config 'weekly_email_hour' must be 0..23")
    if not (0 <= cfg["weekly_email_minute"] <= 59):
        raise ConfigError("Config 'weekly_email_minute' must be 0..59")
    if not (1 <= cfg["smtp_port"] <= 65535):
        raise ConfigError("Config 'smtp_port' must be between 1 and 65535")
    if cfg["ollama_timeout_seconds"] <= 0:
        raise ConfigError("Config 'ollama_timeout_seconds' must be > 0")
    if cfg["smtp_timeout_seconds"] <= 0:
        raise ConfigError("Config 'smtp_timeout_seconds' must be > 0")
    if cfg["desktop_startup_timeout_seconds"] <= 0:
        raise ConfigError("Config 'desktop_startup_timeout_seconds' must be > 0")
    if cfg["desktop_request_timeout_seconds"] <= 0:
        raise ConfigError("Config 'desktop_request_timeout_seconds' must be > 0")
    for key in (
        "quote_cache_ttl_seconds",
        "history_cache_ttl_seconds",
        "enrichment_cache_ttl_seconds",
        "history_bar_cache_ttl_seconds",
    ):
        if cfg[key] <= 0:
            raise ConfigError(f"Config '{key}' must be > 0")
    if not cfg["benchmarks"] or not all(
        isinstance(item, str) and item.strip() for item in cfg["benchmarks"]
    ):
        raise ConfigError("Config 'benchmarks' must be a non-empty list of strings")
    cfg["benchmarks"] = [item.strip().upper() for item in cfg["benchmarks"]]
    cfg["host"] = cfg["host"].strip()
    cfg["ollama_host"] = cfg["ollama_host"].strip().rstrip("/")
    cfg["ollama_model"] = cfg["ollama_model"].strip()
    cfg["smtp_host"] = cfg["smtp_host"].strip()
    for key in EMAIL_SETTING_KEYS:
        cfg[key] = str(cfg[key]).strip()
        if not cfg[key]:
            raise ConfigError(f"Config '{key}' must be non-empty")

    # Normalize floats that may arrive as ints from TOML.
    for key in (
        "desktop_startup_timeout_seconds",
        "desktop_request_timeout_seconds",
        "quote_cache_ttl_seconds",
        "history_cache_ttl_seconds",
        "enrichment_cache_ttl_seconds",
        "history_bar_cache_ttl_seconds",
        "ollama_timeout_seconds",
        "smtp_timeout_seconds",
    ):
        cfg[key] = float(cfg[key])

    return cfg


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONFIG_PATH
    if not config_path.is_file():
        if path is None and EXAMPLE_CONFIG_PATH.is_file():
            config_path = EXAMPLE_CONFIG_PATH
        else:
            raise ConfigError(f"Missing {config_path}.")
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a table of keys")
    return _validate(raw)


def resolve_email_setting(name: str, config: dict[str, Any] | None = None) -> str:
    """
    Resolve an email config value.

    Config may store either an environment-variable name or a direct value:
        os.getenv(config[name], config[name])

    If the configured string is a known env-key default and that variable is
    unset, raise instead of using the key name as the secret/address.
    """
    if name not in EMAIL_SETTING_KEYS:
        raise ConfigError(f"Unknown email setting '{name}'")
    cfg = config if config is not None else CONFIG
    raw = str(cfg[name]).strip()
    if not raw:
        raise ConfigError(f"Config '{name}' must be non-empty")
    value = (os.getenv(raw) or "").strip() or raw
    if value in KNOWN_EMAIL_ENV_KEYS:
        raise ConfigError(
            f"Missing environment variable '{raw}' for config '{name}'"
        )
    return value


CONFIG = load_config()
