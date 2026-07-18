from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.models import Order, Transaction
from app.services import accounts as account_svc
from app.services import trading as trading_svc
from app.services.trading import TradingError

pages_bp = Blueprint("pages", __name__)


def _flash_order_status(order: Order) -> None:
    if order.status == "filled":
        flash("Order filled.", "success")
    elif order.status == "rejected":
        flash(f"Order rejected: {order.error_message}", "error")
    else:
        flash("Order queued.", "success")


def _flash_processed_orders(result: dict[str, list[dict]]) -> None:
    if result["filled"]:
        flash(f"Filled {len(result['filled'])} order(s).", "success")
    if result["rejected"]:
        flash(f"Rejected {len(result['rejected'])} order(s).", "error")


@pages_bp.get("/")
def dashboard():
    accounts = account_svc.list_accounts()
    summaries = [account_svc.account_summary(a) for a in accounts]
    real_accounts = [s for s in summaries if s["type"] == "real"]
    paper_accounts = [s for s in summaries if s["type"] == "paper"]

    real_value = 0.0
    real_day_change = 0.0
    real_priced = True
    real_day_priced = True
    for account in real_accounts:
        if account["equity"] is None:
            real_priced = False
        else:
            real_value += account["equity"]
        if account["day_change"] is None:
            if account["positions"]:
                real_day_priced = False
        else:
            real_day_change += account["day_change"]

    real_total = round(real_value, 2) if real_priced or not real_accounts else None
    real_day = round(real_day_change, 2) if real_day_priced or not real_accounts else None
    prev_real = (real_total - real_day) if real_total is not None and real_day is not None else None
    real_day_pct = (
        round(real_day / prev_real * 100.0, 2) if prev_real else None
    )

    return render_template(
        "dashboard.html",
        real_accounts=real_accounts,
        paper_accounts=paper_accounts,
        has_accounts=bool(summaries),
        real_total=real_total,
        real_day_change=real_day,
        real_day_change_pct=real_day_pct,
    )


@pages_bp.route("/accounts/new", methods=["GET", "POST"])
def account_new():
    if request.method == "POST":
        try:
            account = account_svc.create_account(
                name=request.form.get("name", ""),
                account_type=request.form.get("type", ""),
                starting_cash=float(request.form.get("starting_cash") or 0),
            )
            flash("Account created.", "success")
            return redirect(url_for("pages.account_detail", account_id=account.id))
        except (ValueError, TypeError) as exc:
            flash(str(exc), "error")
    return render_template("account_new.html")


@pages_bp.get("/accounts/<int:account_id>")
def account_detail(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        abort(404)
    processed = trading_svc.process_open_orders(account)
    if processed["filled"] or processed["rejected"]:
        _flash_processed_orders(processed)
        account = account_svc.get_account(account_id)
    summary = account_svc.account_summary(account)
    recent = (
        Transaction.query.filter_by(account_id=account.id)
        .order_by(Transaction.timestamp.desc(), Transaction.id.desc())
        .limit(8)
        .all()
    )
    return render_template(
        "account_detail.html",
        account=summary,
        recent=[account_svc.serialize_transaction(t) for t in recent],
    )


@pages_bp.post("/accounts/<int:account_id>/delete")
def account_delete(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        abort(404)
    account_svc.delete_account(account)
    flash("Account deleted.", "success")
    return redirect(url_for("pages.dashboard"))


@pages_bp.route("/accounts/<int:account_id>/buy", methods=["GET", "POST"])
def buy(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        abort(404)
    summary = account_svc.account_summary(account)
    if request.method == "POST":
        try:
            if account.is_real:
                trading_svc.buy_real(
                    account,
                    symbol=request.form.get("symbol", ""),
                    shares=float(request.form.get("shares")),
                    price=float(request.form.get("price")),
                    fees=float(request.form.get("fees") or 0),
                    timestamp=request.form.get("timestamp") or None,
                    notes=request.form.get("notes") or None,
                )
            else:
                order = trading_svc.place_paper_order(
                    account,
                    side="buy",
                    order_type=request.form.get("order_type", "market"),
                    symbol=request.form.get("symbol", ""),
                    shares=float(request.form.get("shares")),
                    limit_price=request.form.get("limit_price") or None,
                )
                _flash_order_status(order)
            if account.is_real:
                flash("Buy recorded.", "success")
            return redirect(url_for("pages.account_detail", account_id=account.id))
        except (TradingError, ValueError, TypeError) as exc:
            flash(str(exc), "error")
    return render_template("buy.html", account=summary)


@pages_bp.route("/accounts/<int:account_id>/sell", methods=["GET", "POST"])
def sell(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        abort(404)
    summary = account_svc.account_summary(account)
    if request.method == "POST":
        try:
            if account.is_real:
                trading_svc.sell_real(
                    account,
                    symbol=request.form.get("symbol", ""),
                    shares=float(request.form.get("shares")),
                    price=float(request.form.get("price")),
                    fees=float(request.form.get("fees") or 0),
                    timestamp=request.form.get("timestamp") or None,
                    notes=request.form.get("notes") or None,
                )
            else:
                order = trading_svc.place_paper_order(
                    account,
                    side="sell",
                    order_type=request.form.get("order_type", "market"),
                    symbol=request.form.get("symbol", ""),
                    shares=float(request.form.get("shares")),
                    limit_price=request.form.get("limit_price") or None,
                )
                _flash_order_status(order)
            if account.is_real:
                flash("Sell recorded.", "success")
            return redirect(url_for("pages.account_detail", account_id=account.id))
        except (TradingError, ValueError, TypeError) as exc:
            flash(str(exc), "error")
    return render_template("sell.html", account=summary)


@pages_bp.get("/accounts/<int:account_id>/ledger")
def ledger(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        abort(404)
    summary = account_svc.account_summary(account)
    tx_type = request.args.get("type", "").strip().lower()
    query = Transaction.query.filter_by(account_id=account.id)
    if tx_type:
        query = query.filter_by(type=tx_type)
    rows = query.order_by(Transaction.timestamp.desc(), Transaction.id.desc()).all()
    return render_template(
        "ledger.html",
        account=summary,
        transactions=[account_svc.serialize_transaction(t) for t in rows],
        filter_type=tx_type,
    )


@pages_bp.route("/accounts/<int:account_id>/cash", methods=["GET", "POST"])
def cash(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        abort(404)
    if not account.is_paper:
        abort(404)
    summary = account_svc.account_summary(account)
    if request.method == "POST":
        try:
            trading_svc.adjust_cash(
                account,
                amount=float(request.form.get("amount")),
                action=request.form.get("action", "deposit"),
            )
            flash("Cash updated.", "success")
            return redirect(url_for("pages.account_detail", account_id=account.id))
        except (TradingError, ValueError, TypeError) as exc:
            flash(str(exc), "error")
    return render_template("cash.html", account=summary)


@pages_bp.route("/accounts/<int:account_id>/orders", methods=["GET", "POST"])
def orders(account_id: int):
    account = account_svc.get_account(account_id)
    if account is None:
        abort(404)
    if not account.is_paper:
        abort(404)
    processed = trading_svc.process_open_orders(account)
    if processed["filled"] or processed["rejected"]:
        _flash_processed_orders(processed)
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "cancel":
                trading_svc.cancel_order(account, int(request.form.get("order_id")))
                flash("Order cancelled.", "success")
            else:
                order = trading_svc.place_paper_order(
                    account,
                    side=request.form.get("side", "buy"),
                    order_type=request.form.get("order_type", "limit"),
                    symbol=request.form.get("symbol", ""),
                    shares=float(request.form.get("shares")),
                    limit_price=request.form.get("limit_price") or None,
                )
                _flash_order_status(order)
            return redirect(url_for("pages.orders", account_id=account.id))
        except (TradingError, ValueError, TypeError) as exc:
            flash(str(exc), "error")
    summary = account_svc.account_summary(account)
    rows = (
        Order.query.filter_by(account_id=account.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return render_template(
        "orders.html",
        account=summary,
        orders=[trading_svc.serialize_order(o) for o in rows],
    )
