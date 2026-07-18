from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.models import Order, Transaction
from app.services import accounts as account_svc
from app.services import trading as trading_svc
from app.services.quotes import get_quotes
from app.services.trading import TradingError

api_bp = Blueprint("api", __name__)


def _error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


@api_bp.get("/quotes")
def quotes():
    raw = request.args.get("symbols", "")
    symbols = [s.strip() for s in raw.split(",") if s.strip()]
    return jsonify({"ok": True, "quotes": get_quotes(symbols)})


@api_bp.get("/accounts")
def list_accounts():
    items = [account_svc.account_summary(a) for a in account_svc.list_accounts()]
    return jsonify({"ok": True, "accounts": items})


@api_bp.post("/accounts")
def create_account():
    data = request.get_json(silent=True) or {}
    try:
        account = account_svc.create_account(
            name=data.get("name", ""),
            account_type=data.get("type", ""),
            starting_cash=float(data.get("starting_cash") or 0),
            reference_cash=float(data.get("reference_cash") or 0),
        )
    except (ValueError, TypeError) as exc:
        return _error(str(exc))
    return jsonify({"ok": True, "account": account_svc.account_summary(account)}), 201


@api_bp.get("/accounts/<int:account_id>")
def get_account(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        return _error("Account not found", 404)
    trading_svc.try_fill_open_orders(account)
    account = account_svc.get_account(account_id)
    return jsonify({"ok": True, "account": account_svc.account_summary(account)})


@api_bp.post("/accounts/<int:account_id>/buy")
def buy(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        return _error("Account not found", 404)
    data = request.get_json(silent=True) or {}
    try:
        if account.is_real:
            tx = trading_svc.buy_real(
                account,
                symbol=data.get("symbol", ""),
                shares=float(data.get("shares")),
                price=float(data.get("price")),
                fees=float(data.get("fees") or 0),
                timestamp=data.get("timestamp"),
                notes=data.get("notes"),
            )
            return jsonify({"ok": True, "transaction": account_svc.serialize_transaction(tx)})
        result = trading_svc.place_paper_order(
            account,
            side="buy",
            order_type=data.get("order_type", "market"),
            symbol=data.get("symbol", ""),
            shares=float(data.get("shares")),
            limit_price=data.get("limit_price"),
        )
        if isinstance(result, Order):
            return jsonify({"ok": True, "order": trading_svc.serialize_order(result)})
        return jsonify({"ok": True, "transaction": account_svc.serialize_transaction(result)})
    except (TradingError, ValueError, TypeError) as exc:
        return _error(str(exc))


@api_bp.post("/accounts/<int:account_id>/sell")
def sell(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        return _error("Account not found", 404)
    data = request.get_json(silent=True) or {}
    try:
        if account.is_real:
            tx = trading_svc.sell_real(
                account,
                symbol=data.get("symbol", ""),
                shares=float(data.get("shares")),
                price=float(data.get("price")),
                fees=float(data.get("fees") or 0),
                timestamp=data.get("timestamp"),
                notes=data.get("notes"),
            )
            return jsonify({"ok": True, "transaction": account_svc.serialize_transaction(tx)})
        result = trading_svc.place_paper_order(
            account,
            side="sell",
            order_type=data.get("order_type", "market"),
            symbol=data.get("symbol", ""),
            shares=float(data.get("shares")),
            limit_price=data.get("limit_price"),
        )
        if isinstance(result, Order):
            return jsonify({"ok": True, "order": trading_svc.serialize_order(result)})
        return jsonify({"ok": True, "transaction": account_svc.serialize_transaction(result)})
    except (TradingError, ValueError, TypeError) as exc:
        return _error(str(exc))


@api_bp.post("/accounts/<int:account_id>/cash")
def cash(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        return _error("Account not found", 404)
    data = request.get_json(silent=True) or {}
    try:
        tx = trading_svc.adjust_cash(
            account,
            amount=float(data.get("amount")),
            action=data.get("action", "deposit"),
        )
        return jsonify({"ok": True, "transaction": account_svc.serialize_transaction(tx)})
    except (TradingError, ValueError, TypeError) as exc:
        return _error(str(exc))


@api_bp.get("/accounts/<int:account_id>/transactions")
def transactions(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        return _error("Account not found", 404)
    rows = (
        Transaction.query.filter_by(account_id=account.id)
        .order_by(Transaction.timestamp.desc(), Transaction.id.desc())
        .all()
    )
    return jsonify(
        {"ok": True, "transactions": [account_svc.serialize_transaction(t) for t in rows]}
    )


@api_bp.get("/accounts/<int:account_id>/orders")
def orders(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        return _error("Account not found", 404)
    trading_svc.try_fill_open_orders(account)
    rows = (
        Order.query.filter_by(account_id=account.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return jsonify({"ok": True, "orders": [trading_svc.serialize_order(o) for o in rows]})


@api_bp.post("/accounts/<int:account_id>/orders")
def create_order(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        return _error("Account not found", 404)
    data = request.get_json(silent=True) or {}
    try:
        result = trading_svc.place_paper_order(
            account,
            side=data.get("side", "buy"),
            order_type=data.get("order_type", "limit"),
            symbol=data.get("symbol", ""),
            shares=float(data.get("shares")),
            limit_price=data.get("limit_price"),
        )
        if isinstance(result, Order):
            return jsonify({"ok": True, "order": trading_svc.serialize_order(result)}), 201
        return jsonify({"ok": True, "transaction": account_svc.serialize_transaction(result)}), 201
    except (TradingError, ValueError, TypeError) as exc:
        return _error(str(exc))


@api_bp.delete("/accounts/<int:account_id>/orders/<int:order_id>")
def delete_order(account_id: int, order_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        return _error("Account not found", 404)
    try:
        order = trading_svc.cancel_order(account, order_id)
        return jsonify({"ok": True, "order": trading_svc.serialize_order(order)})
    except TradingError as exc:
        return _error(str(exc))
