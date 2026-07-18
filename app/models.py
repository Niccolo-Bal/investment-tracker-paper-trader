from __future__ import annotations

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Account(db.Model):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # real | paper
    cash_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reference_cash: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    positions: Mapped[list[Position]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    orders: Mapped[list[Order]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )

    @property
    def is_paper(self) -> bool:
        return self.type == "paper"

    @property
    def is_real(self) -> bool:
        return self.type == "real"


class Position(db.Model):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    shares: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    account: Mapped[Account] = relationship(back_populates="positions")


class Transaction(db.Model):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fees: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_held_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    account: Mapped[Account] = relationship(back_populates="transactions")


class Order(db.Model):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # buy | sell
    order_type: Mapped[str] = mapped_column(String(8), nullable=False)  # market | limit
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    account: Mapped[Account] = relationship(back_populates="orders")
