from __future__ import annotations

import time
from typing import Any

import yfinance as yf

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 30.0


def get_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Return last price and day change for each symbol. Cached briefly."""
    cleaned = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    if not cleaned:
        return {}

    now = time.monotonic()
    result: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    for symbol in cleaned:
        cached = _CACHE.get(symbol)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            result[symbol] = cached[1]
        else:
            missing.append(symbol)

    if missing:
        fetched = _fetch_quotes(missing)
        for symbol, data in fetched.items():
            _CACHE[symbol] = (now, data)
            result[symbol] = data

    return result


def get_price(symbol: str) -> float | None:
    quotes = get_quotes([symbol])
    data = quotes.get(symbol.strip().upper())
    if not data:
        return None
    return data.get("price")


def _fetch_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = getattr(info, "last_price", None)
            if price is None:
                hist = ticker.history(period="5d")
                if hist.empty or len(hist) == 0:
                    out[symbol] = {"price": None, "change": None, "change_pct": None, "error": "No data"}
                    continue
                price = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
            else:
                price = float(price)
                prev_close = getattr(info, "previous_close", None)
                prev = float(prev_close) if prev_close is not None else price

            change = price - prev
            change_pct = (change / prev * 100.0) if prev else 0.0
            out[symbol] = {
                "price": round(price, 4),
                "change": round(change, 4),
                "change_pct": round(change_pct, 4),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 — surface quote errors to UI
            out[symbol] = {
                "price": None,
                "change": None,
                "change_pct": None,
                "error": str(exc),
            }
    return out
