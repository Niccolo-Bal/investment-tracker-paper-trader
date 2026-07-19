"""Friday-to-Friday market performance, benchmarks, and mover context."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any

import yfinance as yf

from app.config import CONFIG
from app.models import Account, Transaction
from app.services.history import _get_symbol_history, _is_nan

BENCHMARKS = tuple(CONFIG["benchmarks"])
_ENRICHMENT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_ENRICHMENT_TTL_SECONDS = CONFIG["enrichment_cache_ttl_seconds"]
_HISTORY_BAR_CACHE: dict[
    tuple[str, date, date], tuple[float, dict[date, dict[str, float]]]
] = {}
_HISTORY_BAR_TTL_SECONDS = CONFIG["history_bar_cache_ttl_seconds"]


def reporting_period(
    now: datetime | None = None,
    *,
    weekday: int = 4,
    hour: int = 16,
    minute: int = 30,
) -> tuple[datetime, datetime]:
    """
    Return (period_start, period_end) for the most recent completed weekly cutoff.

    End is the latest Friday 4:30 PM (local) that has already passed.
    Start is the previous Friday 4:30 PM.
    A Saturday catch-up still uses that Friday–Friday window.
    """
    local_now = (now or datetime.now().astimezone()).astimezone()
    days_since = (local_now.weekday() - weekday) % 7
    end_date = local_now.date() - timedelta(days=days_since)
    end = datetime.combine(end_date, dt_time(hour, minute)).astimezone()
    if local_now < end:
        end_date -= timedelta(days=7)
        end = datetime.combine(end_date, dt_time(hour, minute)).astimezone()
    start = end - timedelta(days=7)
    return start, end


def _price_on_or_before(
    closes: dict[date, float], boundary: date, lookback_days: int = 10
) -> tuple[date | None, float | None]:
    day = boundary
    for _ in range(lookback_days + 1):
        price = closes.get(day)
        if price is not None:
            return day, price
        day -= timedelta(days=1)
    return None, None


def _get_symbol_bars(
    symbol: str, start: date, end: date
) -> dict[date, dict[str, float]]:
    key = (symbol, start, end)
    cached = _HISTORY_BAR_CACHE.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _HISTORY_BAR_TTL_SECONDS:
        return cached[1]

    history = yf.Ticker(symbol).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        actions=True,
    )
    bars: dict[date, dict[str, float]] = {}
    if not history.empty:
        for index, row in history.iterrows():
            day = index.date()
            close = row.get("Close")
            if close is None or _is_nan(close):
                continue
            volume = row.get("Volume")
            bars[day] = {
                "close": float(close),
                "volume": float(volume)
                if volume is not None and not _is_nan(volume)
                else 0.0,
            }
    _HISTORY_BAR_CACHE[key] = (now, bars)
    return bars


def _tx_time(tx: Transaction) -> datetime:
    ts = tx.timestamp
    if ts.tzinfo is None:
        return ts.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return ts


def _replay_shares(
    transactions: list[Transaction],
    splits: dict[date, list[tuple[str, float]]],
    as_of: datetime,
) -> dict[str, float]:
    """Replay buys/sells/splits for positions owned strictly before `as_of`."""
    shares: dict[str, float] = defaultdict(float)
    ordered = sorted(transactions, key=lambda t: (_tx_time(t), t.id))
    split_events = sorted(
        ((d, sym, ratio) for d, items in splits.items() for sym, ratio in items),
        key=lambda item: item[0],
    )
    split_i = 0
    for tx in ordered:
        ts = _tx_time(tx)
        if ts >= as_of:
            break
        tx_day = ts.date()
        while split_i < len(split_events) and split_events[split_i][0] <= tx_day:
            _, sym, ratio = split_events[split_i]
            if ratio > 0:
                shares[sym] *= ratio
            split_i += 1
        symbol = (tx.symbol or "").upper()
        qty = float(tx.shares or 0.0)
        shares[symbol] += qty if tx.type == "buy" else -qty
    while split_i < len(split_events) and split_events[split_i][0] <= as_of.date():
        _, sym, ratio = split_events[split_i]
        if ratio > 0:
            shares[sym] *= ratio
        split_i += 1
    return {sym: qty for sym, qty in shares.items() if abs(qty) > 1e-12}


def _modified_dietz(
    start_value: float,
    weekly_pnl: float,
    cash_flows: list[tuple[datetime, float]],
    start: datetime,
    end: datetime,
) -> float | None:
    period = (end - start).total_seconds()
    if period <= 0:
        return None
    weighted = 0.0
    for ts, amount in cash_flows:
        remaining = (end - ts).total_seconds()
        weight = max(0.0, min(1.0, remaining / period))
        weighted += weight * amount
    denominator = start_value + weighted
    if abs(denominator) < 1e-9:
        return None
    return weekly_pnl / denominator * 100.0


def _period_flows(
    transactions: list[Transaction], start: datetime, end: datetime
) -> tuple[float, float, list[tuple[datetime, float]], list[dict[str, Any]]]:
    buys = 0.0
    sells = 0.0
    flows: list[tuple[datetime, float]] = []
    activity: list[dict[str, Any]] = []
    for tx in sorted(transactions, key=lambda t: (_tx_time(t), t.id)):
        ts = _tx_time(tx)
        if ts < start or ts >= end:
            continue
        shares = float(tx.shares or 0.0)
        price = float(tx.price or 0.0)
        fees = float(tx.fees or 0.0)
        if tx.type == "buy":
            amount = shares * price + fees
            buys += amount
            flows.append((ts, amount))
        else:
            amount = shares * price - fees
            sells += amount
            flows.append((ts, -amount))
        activity.append(
            {
                "type": tx.type,
                "symbol": (tx.symbol or "").upper(),
                "shares": shares,
                "price": price,
                "fees": fees,
                "realized_pnl": tx.realized_pnl,
                "timestamp": ts.isoformat(),
            }
        )
    return buys, sells, flows, activity


def _symbol_enrichment(symbol: str) -> dict[str, Any]:
    cached = _ENRICHMENT_CACHE.get(symbol)
    now = time.monotonic()
    if cached and now - cached[0] < _ENRICHMENT_TTL_SECONDS:
        return cached[1]

    news: list[dict[str, Any]] = []
    events: dict[str, Any] = {}
    try:
        ticker = yf.Ticker(symbol)
        try:
            items = ticker.get_news(count=8, tab="news") or []
        except Exception:  # noqa: BLE001
            items = []
        for item in items:
            content = item.get("content") if isinstance(item, dict) else None
            if not isinstance(content, dict):
                continue
            pub = content.get("pubDate") or content.get("displayTime") or ""
            title = (content.get("title") or "").strip()
            if not title:
                continue
            url = None
            for key in ("canonicalUrl", "clickThroughUrl"):
                raw = content.get(key)
                if isinstance(raw, dict):
                    url = raw.get("url")
                elif isinstance(raw, str):
                    url = raw
                if url:
                    break
            provider = None
            provider_raw = content.get("provider")
            if isinstance(provider_raw, dict):
                provider = provider_raw.get("displayName")
            news.append(
                {
                    "title": title[:180],
                    "summary": (
                        (content.get("summary") or content.get("description") or "")[
                            :280
                        ]
                    ),
                    "published": str(pub)[:30],
                    "provider": provider,
                    "url": url,
                }
            )
            if len(news) >= 3:
                break
        try:
            calendar = ticker.get_calendar() or {}
            if isinstance(calendar, dict):
                events = {
                    key: calendar.get(key)
                    for key in (
                        "Earnings Date",
                        "Dividend Date",
                        "Ex-Dividend Date",
                        "Earnings High",
                        "Earnings Low",
                        "Earnings Average",
                    )
                    if calendar.get(key) is not None
                }
        except Exception:  # noqa: BLE001
            events = {}
    except Exception:  # noqa: BLE001
        news = []
        events = {}

    payload = {"news": news, "events": events}
    _ENRICHMENT_CACHE[symbol] = (now, payload)
    return payload


def _daily_observations(
    symbol_bars: dict[date, dict[str, float]], start: date, end: date
) -> list[dict[str, Any]]:
    days = sorted(d for d in symbol_bars if start <= d <= end)
    rows: list[dict[str, Any]] = []
    prev_close = None
    for day in days:
        close = symbol_bars[day]["close"]
        volume = symbol_bars[day].get("volume")
        change_pct = None
        if prev_close:
            change_pct = (close - prev_close) / prev_close * 100.0
        rows.append(
            {
                "date": day.isoformat(),
                "close": round(close, 4),
                "volume": volume,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
            }
        )
        prev_close = close
    return rows


def build_weekly_performance(
    accounts: list[Account],
    *,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, Any]:
    """Build transaction-adjusted weekly performance for real accounts."""
    hist_start = period_start.date() - timedelta(days=14)
    hist_end = period_end.date() + timedelta(days=2)

    all_txs: list[Transaction] = []
    account_txs: dict[int, list[Transaction]] = {}
    for account in accounts:
        txs = (
            Transaction.query.filter(
                Transaction.account_id == account.id,
                Transaction.type.in_(("buy", "sell")),
                Transaction.symbol.isnot(None),
                Transaction.shares.isnot(None),
            )
            .order_by(Transaction.timestamp.asc(), Transaction.id.asc())
            .all()
        )
        account_txs[account.id] = txs
        all_txs.extend(txs)

    symbols = sorted(
        {(tx.symbol or "").upper() for tx in all_txs if tx.symbol} | set(BENCHMARKS)
    )

    closes: dict[str, dict[date, float]] = {}
    splits_by_day: dict[date, list[tuple[str, float]]] = defaultdict(list)
    bars: dict[str, dict[date, dict[str, float]]] = {}
    for symbol in symbols:
        symbol_closes, symbol_splits = _get_symbol_history(symbol, hist_start, hist_end)
        closes[symbol] = symbol_closes
        bars[symbol] = _get_symbol_bars(symbol, hist_start, hist_end)
        for split_date, ratio in symbol_splits.items():
            splits_by_day[split_date].append((symbol, ratio))

    benchmarks: dict[str, Any] = {}
    for symbol in BENCHMARKS:
        start_day, start_px = _price_on_or_before(
            closes.get(symbol, {}), period_start.date()
        )
        end_day, end_px = _price_on_or_before(closes.get(symbol, {}), period_end.date())
        change_pct = None
        if start_px and end_px:
            change_pct = (end_px - start_px) / start_px * 100.0
        benchmarks[symbol] = {
            "start_date": start_day.isoformat() if start_day else None,
            "end_date": end_day.isoformat() if end_day else None,
            "start_price": round(start_px, 4) if start_px is not None else None,
            "end_price": round(end_px, 4) if end_px is not None else None,
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
        }

    account_rows: list[dict[str, Any]] = []
    symbol_rows: list[dict[str, Any]] = []
    enrichment: dict[str, dict[str, Any]] = {}

    portfolio_start = 0.0
    portfolio_end = 0.0
    portfolio_buys = 0.0
    portfolio_sells = 0.0
    portfolio_flows: list[tuple[datetime, float]] = []
    priced_ok = True

    for account in accounts:
        txs = account_txs.get(account.id, [])
        start_shares = _replay_shares(txs, splits_by_day, period_start)
        end_shares = _replay_shares(txs, splits_by_day, period_end)
        buys, sells, flows, activity = _period_flows(txs, period_start, period_end)

        start_value = 0.0
        end_value = 0.0
        account_priced = True
        per_symbol: dict[str, dict[str, Any]] = {}

        relevant_symbols = sorted(
            set(start_shares) | set(end_shares) | {a["symbol"] for a in activity}
        )

        for symbol in relevant_symbols:
            s_shares = start_shares.get(symbol, 0.0)
            e_shares = end_shares.get(symbol, 0.0)
            start_day, start_px = _price_on_or_before(
                closes.get(symbol, {}), period_start.date()
            )
            end_day, end_px = _price_on_or_before(
                closes.get(symbol, {}), period_end.date()
            )

            if s_shares and start_px is None:
                for tx in reversed(txs):
                    if (
                        (tx.symbol or "").upper() == symbol
                        and tx.price is not None
                        and _tx_time(tx) < period_start
                    ):
                        start_px = float(tx.price)
                        start_day = _tx_time(tx).date()
                        break
            if e_shares and end_px is None:
                for tx in reversed(txs):
                    if (
                        (tx.symbol or "").upper() == symbol
                        and tx.price is not None
                        and _tx_time(tx) < period_end
                    ):
                        end_px = float(tx.price)
                        end_day = _tx_time(tx).date()
                        break

            if (s_shares and start_px is None) or (e_shares and end_px is None):
                account_priced = False
                priced_ok = False

            s_val = (s_shares * start_px) if start_px is not None else 0.0
            e_val = (e_shares * end_px) if end_px is not None else 0.0
            start_value += s_val
            end_value += e_val

            sym_buys = 0.0
            sym_sells = 0.0
            sym_flows: list[tuple[datetime, float]] = []
            for tx in txs:
                ts = _tx_time(tx)
                if ts < period_start or ts >= period_end:
                    continue
                if (tx.symbol or "").upper() != symbol:
                    continue
                sh = float(tx.shares or 0.0)
                price = float(tx.price or 0.0)
                fees = float(tx.fees or 0.0)
                if tx.type == "buy":
                    amount = sh * price + fees
                    sym_buys += amount
                    sym_flows.append((ts, amount))
                else:
                    amount = sh * price - fees
                    sym_sells += amount
                    sym_flows.append((ts, -amount))

            weekly_pnl = e_val - s_val - sym_buys + sym_sells
            price_chg_pct = None
            if start_px and end_px:
                price_chg_pct = (end_px - start_px) / start_px * 100.0
            weekly_pct = _modified_dietz(
                s_val, weekly_pnl, sym_flows, period_start, period_end
            )
            if weekly_pct is None and not sym_flows and s_val:
                weekly_pct = weekly_pnl / s_val * 100.0

            spy_pct = benchmarks.get("SPY", {}).get("change_pct")
            vs_spy = (
                round(price_chg_pct - spy_pct, 2)
                if price_chg_pct is not None and spy_pct is not None
                else None
            )

            if symbol not in enrichment:
                enrichment[symbol] = _symbol_enrichment(symbol)

            row = {
                "account_id": account.id,
                "account_name": account.name,
                "symbol": symbol,
                "start_shares": round(s_shares, 6),
                "end_shares": round(e_shares, 6),
                "start_price": round(start_px, 4) if start_px is not None else None,
                "end_price": round(end_px, 4) if end_px is not None else None,
                "start_date": start_day.isoformat() if start_day else None,
                "end_date": end_day.isoformat() if end_day else None,
                "start_value": round(s_val, 2),
                "end_value": round(e_val, 2),
                "buys": round(sym_buys, 2),
                "sells": round(sym_sells, 2),
                "weekly_pnl": round(weekly_pnl, 2),
                "weekly_pct": round(weekly_pct, 2) if weekly_pct is not None else None,
                "price_change_pct": (
                    round(price_chg_pct, 2) if price_chg_pct is not None else None
                ),
                "vs_spy_pct": vs_spy,
                "daily": _daily_observations(
                    bars.get(symbol, {}), period_start.date(), period_end.date()
                ),
                "news": enrichment[symbol].get("news", []),
                "events": enrichment[symbol].get("events", {}),
            }
            per_symbol[symbol] = row
            symbol_rows.append(row)

        weekly_pnl = end_value - start_value - buys + sells
        weekly_pct = _modified_dietz(
            start_value, weekly_pnl, flows, period_start, period_end
        )
        if weekly_pct is None and not flows and start_value:
            weekly_pct = weekly_pnl / start_value * 100.0

        for row in per_symbol.values():
            row["end_weight_pct"] = (
                round(row["end_value"] / end_value * 100.0, 2) if end_value else None
            )
            row["start_weight_pct"] = (
                round(row["start_value"] / start_value * 100.0, 2)
                if start_value
                else None
            )

        account_rows.append(
            {
                "id": account.id,
                "name": account.name,
                "start_value": round(start_value, 2) if account_priced else None,
                "end_value": round(end_value, 2) if account_priced else None,
                "buys": round(buys, 2),
                "sells": round(sells, 2),
                "weekly_change": round(weekly_pnl, 2) if account_priced else None,
                "weekly_change_pct": (
                    round(weekly_pct, 2)
                    if weekly_pct is not None and account_priced
                    else None
                ),
                "activity": activity,
                "symbols": list(per_symbol.values()),
            }
        )

        if account_priced:
            portfolio_start += start_value
            portfolio_end += end_value
            portfolio_buys += buys
            portfolio_sells += sells
            portfolio_flows.extend(flows)

    portfolio_pnl = (
        portfolio_end - portfolio_start - portfolio_buys + portfolio_sells
    )
    portfolio_pct = _modified_dietz(
        portfolio_start, portfolio_pnl, portfolio_flows, period_start, period_end
    )
    if portfolio_pct is None and not portfolio_flows and portfolio_start:
        portfolio_pct = portfolio_pnl / portfolio_start * 100.0

    symbol_rows.sort(key=lambda r: (-abs(r.get("weekly_pnl") or 0.0), r["symbol"]))
    movers = {
        "gainers": sorted(
            [r for r in symbol_rows if (r.get("weekly_pnl") or 0) > 0],
            key=lambda r: -(r.get("weekly_pnl") or 0),
        )[:5],
        "losers": sorted(
            [r for r in symbol_rows if (r.get("weekly_pnl") or 0) < 0],
            key=lambda r: (r.get("weekly_pnl") or 0),
        )[:5],
    }

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "priced": priced_ok or not accounts,
        "totals": {
            "start_value": (
                round(portfolio_start, 2) if priced_ok or not accounts else None
            ),
            "end_value": (
                round(portfolio_end, 2) if priced_ok or not accounts else None
            ),
            "buys": round(portfolio_buys, 2),
            "sells": round(portfolio_sells, 2),
            "weekly_change": (
                round(portfolio_pnl, 2) if priced_ok or not accounts else None
            ),
            "weekly_change_pct": (
                round(portfolio_pct, 2)
                if portfolio_pct is not None and (priced_ok or not accounts)
                else None
            ),
        },
        "accounts": account_rows,
        "symbols": symbol_rows,
        "movers": movers,
        "benchmarks": benchmarks,
    }
