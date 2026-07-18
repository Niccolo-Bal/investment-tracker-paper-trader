from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.models import Order, Transaction
from app.services import accounts as account_svc
from app.services import trading as trading_svc
from app.services.trading import TradingError

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def dashboard():
    accounts = account_svc.list_accounts()
    summaries = [account_svc.account_summary(a) for a in accounts]
    total_equity = sum(s["equity"] or 0 for s in summaries)
    total_pnl = sum(s["total_pnl"] or 0 for s in summaries if s["total_pnl"] is not None)
    open_positions = sum(len(s["positions"]) for s in summaries)
    return render_template(
        "dashboard.html",
        accounts=summaries,
        total_equity=total_equity,
        total_pnl=total_pnl,
        open_positions=open_positions,
    )


@pages_bp.route("/accounts/new", methods=["GET", "POST"])
def account_new():
    if request.method == "POST":
        try:
            account = account_svc.create_account(
                name=request.form.get("name", ""),
                account_type=request.form.get("type", ""),
                starting_cash=float(request.form.get("starting_cash") or 0),
                reference_cash=float(request.form.get("reference_cash") or 0),
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
    filled = trading_svc.try_fill_open_orders(account)
    if filled:
        flash(f"Filled {len(filled)} limit order(s).", "success")
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
                trading_svc.place_paper_order(
                    account,
                    side="buy",
                    order_type=request.form.get("order_type", "market"),
                    symbol=request.form.get("symbol", ""),
                    shares=float(request.form.get("shares")),
                    limit_price=request.form.get("limit_price") or None,
                )
            flash("Buy submitted.", "success")
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
                trading_svc.place_paper_order(
                    account,
                    side="sell",
                    order_type=request.form.get("order_type", "market"),
                    symbol=request.form.get("symbol", ""),
                    shares=float(request.form.get("shares")),
                    limit_price=request.form.get("limit_price") or None,
                )
            flash("Sell submitted.", "success")
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
    filled = trading_svc.try_fill_open_orders(account)
    if filled:
        flash(f"Filled {len(filled)} limit order(s).", "success")
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "cancel":
                trading_svc.cancel_order(account, int(request.form.get("order_id")))
                flash("Order cancelled.", "success")
            else:
                trading_svc.place_paper_order(
                    account,
                    side=request.form.get("side", "buy"),
                    order_type="limit",
                    symbol=request.form.get("symbol", ""),
                    shares=float(request.form.get("shares")),
                    limit_price=request.form.get("limit_price"),
                )
                flash("Limit order placed.", "success")
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
