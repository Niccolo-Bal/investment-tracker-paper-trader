from __future__ import annotations

from datetime import datetime

from app.models import Account, Order, Position, Transaction, db, utcnow
from app.services.accounts import parse_timestamp
from app.services.quotes import get_price, get_quotes


class TradingError(Exception):
    pass


def _get_or_create_position(account: Account, symbol: str) -> Position:
    symbol = symbol.strip().upper()
    position = Position.query.filter_by(account_id=account.id, symbol=symbol).first()
    if position is None:
        position = Position(account_id=account.id, symbol=symbol, shares=0.0, avg_cost=0.0)
        db.session.add(position)
        db.session.flush()
    return position


def _apply_buy(
    account: Account,
    symbol: str,
    shares: float,
    price: float,
    fees: float,
    timestamp: datetime,
    notes: str | None = None,
) -> Transaction:
    if shares <= 0 or price < 0:
        raise TradingError("Shares must be positive and price must be non-negative")
    fees = float(fees or 0.0)
    cost = shares * price + fees

    if account.is_paper:
        if account.cash_balance < cost:
            raise TradingError("Insufficient cash for this purchase")
        account.cash_balance -= cost

    position = _get_or_create_position(account, symbol)
    total_shares = position.shares + shares
    if total_shares <= 0:
        raise TradingError("Invalid share total")
    if position.shares <= 0:
        position.avg_cost = price
        position.opened_at = timestamp
    else:
        position.avg_cost = (
            (position.avg_cost * position.shares) + (price * shares)
        ) / total_shares
    position.shares = total_shares

    tx = Transaction(
        account_id=account.id,
        type="buy",
        symbol=symbol.strip().upper(),
        shares=shares,
        price=price,
        fees=fees,
        timestamp=timestamp,
        notes=notes,
    )
    db.session.add(tx)
    return tx


def _apply_sell(
    account: Account,
    symbol: str,
    shares: float,
    price: float,
    fees: float,
    timestamp: datetime,
    notes: str | None = None,
) -> Transaction:
    if shares <= 0 or price < 0:
        raise TradingError("Shares must be positive and price must be non-negative")
    fees = float(fees or 0.0)
    symbol = symbol.strip().upper()

    position = Position.query.filter_by(account_id=account.id, symbol=symbol).first()
    if position is None or position.shares < shares:
        raise TradingError("Not enough shares to sell")

    proceeds = shares * price - fees
    if account.is_paper:
        account.cash_balance += proceeds

    cost_basis = position.avg_cost * shares
    realized = proceeds - cost_basis
    opened = position.opened_at or timestamp
    if opened.tzinfo is None:
        from datetime import timezone

        opened = opened.replace(tzinfo=timezone.utc)
    time_held = max(0, int((timestamp - opened).total_seconds()))

    position.shares -= shares
    if position.shares <= 1e-12:
        position.shares = 0.0
        position.avg_cost = 0.0

    tx = Transaction(
        account_id=account.id,
        type="sell",
        symbol=symbol,
        shares=shares,
        price=price,
        fees=fees,
        realized_pnl=realized,
        time_held_seconds=time_held,
        timestamp=timestamp,
        notes=notes,
    )
    db.session.add(tx)
    return tx


def buy_real(
    account: Account,
    symbol: str,
    shares: float,
    price: float,
    fees: float = 0.0,
    timestamp: str | None = None,
    notes: str | None = None,
) -> Transaction:
    if not account.is_real:
        raise TradingError("This endpoint is for real accounts")
    tx = _apply_buy(account, symbol, float(shares), float(price), fees, parse_timestamp(timestamp), notes)
    db.session.commit()
    return tx


def sell_real(
    account: Account,
    symbol: str,
    shares: float,
    price: float,
    fees: float = 0.0,
    timestamp: str | None = None,
    notes: str | None = None,
) -> Transaction:
    if not account.is_real:
        raise TradingError("This endpoint is for real accounts")
    tx = _apply_sell(account, symbol, float(shares), float(price), fees, parse_timestamp(timestamp), notes)
    db.session.commit()
    return tx


def place_paper_order(
    account: Account,
    side: str,
    order_type: str,
    symbol: str,
    shares: float,
    limit_price: float | None = None,
) -> Order | Transaction:
    if not account.is_paper:
        raise TradingError("This endpoint is for paper accounts")
    side = side.lower()
    order_type = order_type.lower()
    if side not in ("buy", "sell"):
        raise TradingError("Side must be buy or sell")
    if order_type not in ("market", "limit"):
        raise TradingError("Order type must be market or limit")
    shares = float(shares)
    if shares <= 0:
        raise TradingError("Shares must be positive")
    symbol = symbol.strip().upper()

    if order_type == "market":
        price = get_price(symbol)
        if price is None:
            raise TradingError(f"Could not get market price for {symbol}")
        if side == "buy":
            tx = _apply_buy(account, symbol, shares, price, 0.0, utcnow())
        else:
            tx = _apply_sell(account, symbol, shares, price, 0.0, utcnow())
        db.session.commit()
        return tx

    if limit_price is None or float(limit_price) <= 0:
        raise TradingError("Limit price is required for limit orders")

    if side == "sell":
        position = Position.query.filter_by(account_id=account.id, symbol=symbol).first()
        open_sells = (
            db.session.query(db.func.coalesce(db.func.sum(Order.shares), 0.0))
            .filter(
                Order.account_id == account.id,
                Order.symbol == symbol,
                Order.side == "sell",
                Order.status == "open",
            )
            .scalar()
        )
        available = (position.shares if position else 0.0) - float(open_sells or 0.0)
        if available < shares:
            raise TradingError("Not enough shares available for this sell order")

    order = Order(
        account_id=account.id,
        side=side,
        order_type="limit",
        symbol=symbol,
        shares=shares,
        limit_price=float(limit_price),
        status="open",
    )
    db.session.add(order)
    db.session.commit()
    return order


def cancel_order(account: Account, order_id: int) -> Order:
    order = db.session.get(Order, order_id)
    if order is None or order.account_id != account.id:
        raise TradingError("Order not found")
    if order.status != "open":
        raise TradingError("Only open orders can be cancelled")
    order.status = "cancelled"
    db.session.commit()
    return order


def adjust_cash(account: Account, amount: float, action: str) -> Transaction:
    if not account.is_paper:
        raise TradingError("Cash adjustments are only for paper accounts")
    amount = float(amount)
    if amount <= 0:
        raise TradingError("Amount must be positive")
    action = action.lower()
    if action == "deposit":
        account.cash_balance += amount
        tx = Transaction(
            account_id=account.id,
            type="deposit",
            price=amount,
            fees=0.0,
            notes="Cash deposit",
        )
    elif action == "withdraw":
        if account.cash_balance < amount:
            raise TradingError("Insufficient cash to withdraw")
        account.cash_balance -= amount
        tx = Transaction(
            account_id=account.id,
            type="withdraw",
            price=amount,
            fees=0.0,
            notes="Cash withdrawal",
        )
    else:
        raise TradingError("Action must be deposit or withdraw")
    db.session.add(tx)
    db.session.commit()
    return tx


def try_fill_open_orders(account: Account) -> list[dict]:
    """Attempt to fill open limit orders against current quotes."""
    if not account.is_paper:
        return []

    open_orders = (
        Order.query.filter_by(account_id=account.id, status="open")
        .order_by(Order.created_at.asc())
        .all()
    )
    if not open_orders:
        return []

    symbols = list({o.symbol for o in open_orders})
    quotes = get_quotes(symbols)
    filled: list[dict] = []

    for order in open_orders:
        quote = quotes.get(order.symbol, {})
        price = quote.get("price")
        if price is None or order.limit_price is None:
            continue

        should_fill = False
        if order.side == "buy" and price <= order.limit_price:
            should_fill = True
            fill_price = min(price, order.limit_price)
        elif order.side == "sell" and price >= order.limit_price:
            should_fill = True
            fill_price = max(price, order.limit_price)
        else:
            continue

        if not should_fill:
            continue

        try:
            if order.side == "buy":
                _apply_buy(account, order.symbol, order.shares, fill_price, 0.0, utcnow())
            else:
                _apply_sell(account, order.symbol, order.shares, fill_price, 0.0, utcnow())
            order.status = "filled"
            order.filled_at = utcnow()
            order.fill_price = fill_price
            filled.append(
                {
                    "id": order.id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "shares": order.shares,
                    "fill_price": fill_price,
                }
            )
        except TradingError:
            # Leave open if e.g. insufficient cash at fill time
            continue

    if filled:
        db.session.commit()
    return filled


def serialize_order(order: Order) -> dict:
    return {
        "id": order.id,
        "side": order.side,
        "order_type": order.order_type,
        "symbol": order.symbol,
        "shares": order.shares,
        "limit_price": order.limit_price,
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "filled_at": order.filled_at.isoformat() if order.filled_at else None,
        "fill_price": order.fill_price,
    }
