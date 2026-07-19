from __future__ import annotations

import math
import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import yfinance as yf

from app.config import CONFIG
from app.models import Account, Transaction

_HISTORY_CACHE: dict[
    tuple[str, date, date], tuple[float, dict[date, float], dict[date, float]]
] = {}
_HISTORY_CACHE_TTL_SECONDS = CONFIG["history_cache_ttl_seconds"]


def real_portfolio_history(account: Account) -> dict[str, Any]:
    """Build end-of-day market values by replaying a real account's trades."""
    if not account.is_real:
        raise ValueError("Portfolio backtracking is only available for real accounts")

    transactions = (
        Transaction.query.filter(
            Transaction.account_id == account.id,
            Transaction.type.in_(("buy", "sell")),
            Transaction.symbol.isnot(None),
            Transaction.shares.isnot(None),
        )
        .order_by(Transaction.timestamp.asc(), Transaction.id.asc())
        .all()
    )
    if not transactions:
        return {"points": [], "start": None, "end": None}

    start = min(tx.timestamp.date() for tx in transactions)
    end = date.today()
    symbols = sorted({tx.symbol.upper() for tx in transactions if tx.symbol})

    closes: dict[str, dict[date, float]] = {}
    splits: dict[date, list[tuple[str, float]]] = defaultdict(list)
    for symbol in symbols:
        symbol_closes, symbol_splits = _get_symbol_history(symbol, start, end)
        closes[symbol] = symbol_closes
        for split_date, ratio in symbol_splits.items():
            splits[split_date].append((symbol, ratio))

    shares: dict[str, float] = defaultdict(float)
    last_prices: dict[str, float] = {}
    points: list[dict[str, Any]] = []
    transaction_index = 0

    for day in _business_days(start, end):
        # Splits are effective before trades made during that session.
        for symbol, ratio in splits.get(day, []):
            if ratio > 0:
                shares[symbol] *= ratio

        # Weekend-dated entries take effect on the next business-day point.
        while (
            transaction_index < len(transactions)
            and transactions[transaction_index].timestamp.date() <= day
        ):
            tx = transactions[transaction_index]
            symbol = tx.symbol.upper()
            quantity = float(tx.shares or 0.0)
            shares[symbol] += quantity if tx.type == "buy" else -quantity
            if tx.price is not None:
                # Useful fallback when Yahoo has no close for the purchase date.
                last_prices[symbol] = float(tx.price)
            transaction_index += 1

        for symbol in symbols:
            close = closes[symbol].get(day)
            if close is not None:
                last_prices[symbol] = close

        value = 0.0
        has_unpriced_position = False
        for symbol, quantity in shares.items():
            if quantity <= 1e-12:
                continue
            price = last_prices.get(symbol)
            if price is None:
                has_unpriced_position = True
                break
            value += quantity * price

        if not has_unpriced_position:
            points.append({"date": day.isoformat(), "value": round(value, 2)})

    return {
        "points": points,
        "start": points[0]["date"] if points else None,
        "end": points[-1]["date"] if points else None,
    }


def _business_days(start: date, end: date):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


def _get_symbol_history(
    symbol: str, start: date, end: date
) -> tuple[dict[date, float], dict[date, float]]:
    key = (symbol, start, end)
    cached = _HISTORY_CACHE.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _HISTORY_CACHE_TTL_SECONDS:
        return cached[1], cached[2]

    history = yf.Ticker(symbol).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        actions=True,
    )
    closes: dict[date, float] = {}
    splits: dict[date, float] = {}
    if not history.empty:
        for index, row in history.iterrows():
            day = index.date()
            close = row.get("Close")
            if close is not None and not _is_nan(close):
                closes[day] = float(close)
            ratio = row.get("Stock Splits")
            if ratio is not None and not _is_nan(ratio) and float(ratio) > 0:
                splits[day] = float(ratio)

    _HISTORY_CACHE[key] = (now, closes, splits)
    return closes, splits


def _is_nan(value: Any) -> bool:
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return False
