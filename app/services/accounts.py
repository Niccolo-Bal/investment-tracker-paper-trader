from __future__ import annotations

from datetime import datetime

from app.models import Account, Position, Transaction, db
from app.services.quotes import get_quotes


def create_account(
    name: str,
    account_type: str,
    starting_cash: float = 0.0,
) -> Account:
    if account_type not in ("real", "paper"):
        raise ValueError("Account type must be 'real' or 'paper'")
    name = name.strip()
    if not name:
        raise ValueError("Account name is required")

    account = Account(
        name=name,
        type=account_type,
        cash_balance=float(starting_cash) if account_type == "paper" else 0.0,
    )
    db.session.add(account)

    if account_type == "paper" and starting_cash:
        db.session.flush()
        db.session.add(
            Transaction(
                account_id=account.id,
                type="deposit",
                price=float(starting_cash),
                shares=None,
                symbol=None,
                fees=0.0,
                notes="Starting cash",
            )
        )

    db.session.commit()
    return account


def list_accounts() -> list[Account]:
    return Account.query.order_by(Account.created_at.desc()).all()


def get_account(account_id: int) -> Account | None:
    return db.session.get(Account, account_id)


def delete_account(account: Account) -> None:
    db.session.delete(account)
    db.session.commit()


def serialize_position(position: Position, quote: dict | None = None) -> dict:
    price = quote.get("price") if quote else None
    market_value = (price * position.shares) if price is not None else None
    cost_basis = position.avg_cost * position.shares
    unrealized = (market_value - cost_basis) if market_value is not None else None
    unrealized_pct = (unrealized / cost_basis * 100.0) if unrealized is not None and cost_basis else None
    return {
        "id": position.id,
        "symbol": position.symbol,
        "shares": position.shares,
        "avg_cost": position.avg_cost,
        "cost_basis": round(cost_basis, 2),
        "price": price,
        "market_value": round(market_value, 2) if market_value is not None else None,
        "unrealized_pnl": round(unrealized, 2) if unrealized is not None else None,
        "unrealized_pnl_pct": round(unrealized_pct, 2) if unrealized_pct is not None else None,
        "day_change": quote.get("change") if quote else None,
        "day_change_pct": quote.get("change_pct") if quote else None,
        "opened_at": position.opened_at.isoformat() if position.opened_at else None,
    }


def account_summary(account: Account) -> dict:
    symbols = [p.symbol for p in account.positions if p.shares > 0]
    quotes = get_quotes(symbols) if symbols else {}

    positions_data = []
    holdings_value = 0.0
    cost_basis_total = 0.0
    day_change = 0.0
    priced_all = True
    day_priced_all = True

    for position in account.positions:
        if position.shares <= 0:
            continue
        quote = quotes.get(position.symbol, {})
        row = serialize_position(position, quote)
        positions_data.append(row)
        cost_basis_total += position.avg_cost * position.shares
        if row["market_value"] is not None:
            holdings_value += row["market_value"]
        else:
            priced_all = False
        if row["day_change"] is not None:
            day_change += row["day_change"] * position.shares
        else:
            day_priced_all = False

    cash = account.cash_balance if account.is_paper else 0.0
    equity = holdings_value + cash if priced_all or not symbols else None
    realized = float(
        db.session.query(db.func.coalesce(db.func.sum(Transaction.realized_pnl), 0.0))
        .filter(
            Transaction.account_id == account.id,
            Transaction.type == "sell",
            Transaction.realized_pnl.isnot(None),
        )
        .scalar()
        or 0.0
    )

    if account.is_paper:
        net_capital = _net_deposits(account)
        total_pnl = (equity - net_capital) if equity is not None else None
        total_pnl_pct = (
            (total_pnl / net_capital * 100.0) if total_pnl is not None and net_capital else None
        )
        invested = net_capital
    else:
        buy_fees = sum(
            tx.fees for tx in account.transactions if tx.type == "buy"
        )
        invested = sum(
            (tx.price or 0.0) * (tx.shares or 0.0) + tx.fees
            for tx in account.transactions
            if tx.type == "buy"
        )
        total_pnl = (
            holdings_value - cost_basis_total + realized - buy_fees
            if priced_all or not symbols
            else None
        )
        total_pnl_pct = (
            (total_pnl / invested * 100.0)
            if total_pnl is not None and invested
            else None
        )

    day_change_out = round(day_change, 2) if (day_priced_all or not symbols) else None
    prev_value = (equity - day_change) if equity is not None and day_change_out is not None else None
    day_change_pct = (
        (day_change / prev_value * 100.0) if prev_value else None
    )

    return {
        "id": account.id,
        "name": account.name,
        "type": account.type,
        "cash_balance": round(cash, 2),
        "holdings_value": round(holdings_value, 2),
        "cost_basis": round(cost_basis_total, 2),
        "equity": round(equity, 2) if equity is not None else None,
        "invested": round(invested, 2) if invested is not None else None,
        "unrealized_pnl": round(holdings_value - cost_basis_total, 2)
        if (priced_all or not symbols)
        else None,
        "total_pnl": round(total_pnl, 2) if total_pnl is not None else None,
        "total_pnl_pct": round(total_pnl_pct, 2) if total_pnl_pct is not None else None,
        "day_change": day_change_out,
        "day_change_pct": round(day_change_pct, 2) if day_change_pct is not None else None,
        "realized_pnl": round(realized, 2),
        "positions": positions_data,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "open_orders": sum(1 for o in account.orders if o.status == "open"),
    }


def _net_deposits(account: Account) -> float:
    deposits = sum(t.price or 0.0 for t in account.transactions if t.type == "deposit")
    withdraws = sum(t.price or 0.0 for t in account.transactions if t.type == "withdraw")
    return deposits - withdraws


def serialize_transaction(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "type": tx.type,
        "symbol": tx.symbol,
        "shares": tx.shares,
        "price": tx.price,
        "fees": tx.fees,
        "realized_pnl": tx.realized_pnl,
        "time_held_seconds": tx.time_held_seconds,
        "notes": tx.notes,
        "timestamp": tx.timestamp.isoformat() if tx.timestamp else None,
    }


def parse_timestamp(value: str | None) -> datetime:
    from app.models import utcnow

    if not value:
        return utcnow()
    # Accept ISO or datetime-local (YYYY-MM-DDTHH:MM)
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError("Invalid timestamp") from exc
    if dt.tzinfo is None:
        from datetime import timezone

        dt = dt.replace(tzinfo=timezone.utc)
    return dt
