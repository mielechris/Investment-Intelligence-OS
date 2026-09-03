from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from .models import Book

TACTICAL_BUDGET = 3_000.0
STRATEGIC_BUDGET = 5_000.0
RESERVE_BUDGET = 2_000.0
TOTAL_BUDGET = 10_000.0


@dataclass(frozen=True)
class FillModel:
    spread_bps: float = 8.0
    slippage_bps: float = 12.0
    fill_ratio: float = 1.0

    def fill(self, side: str, quantity: float, reference_price: float) -> tuple[float, float]:
        if quantity <= 0 or reference_price <= 0 or not 0 < self.fill_ratio <= 1:
            raise ValueError("positive quantity/price and fill_ratio in (0, 1] required")
        direction = 1 if side.upper() == "BUY" else -1
        price = reference_price * (1 + direction * (self.spread_bps / 2 + self.slippage_bps) / 10_000)
        return round(quantity * self.fill_ratio, 8), round(price, 8)


@dataclass
class PaperPosition:
    instrument: str
    quantity: float
    average_cost: float
    market_price: float
    thesis: str
    invalidation: str
    correlation_cluster: str = "UNKNOWN"

    @property
    def market_value(self) -> float:
        return self.quantity * self.market_price


@dataclass
class PaperBook:
    name: Book
    maximum_allocation: float
    cash: float
    realized_pnl: float = 0.0
    daily_realized_pnl: float = 0.0
    loss_day: str = field(default_factory=lambda: date.today().isoformat())
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    last_trade_at: str | None = None
    classifications: list[dict[str, Any]] = field(default_factory=list)

    @property
    def nav(self) -> float:
        return self.cash + sum(position.market_value for position in self.positions.values())


@dataclass(frozen=True)
class TacticalPolicy:
    max_position_pct: float = 0.20
    daily_loss_limit_pct: float = 0.03
    cooldown_minutes: int = 30
    max_concurrent_positions: int = 5


@dataclass(frozen=True)
class StrategicPolicy:
    max_position_pct: float = 0.30
    max_cluster_pct: float = 0.45
    max_concurrent_positions: int = 8


class DualBookPortfolio:
    """Pure in-memory paper simulation. It has no ledger or broker imports."""

    def __init__(self) -> None:
        if TACTICAL_BUDGET + STRATEGIC_BUDGET + RESERVE_BUDGET != TOTAL_BUDGET:
            raise RuntimeError("dual-book allocation invariant violated")
        self.tactical = PaperBook(Book.TACTICAL, TACTICAL_BUDGET, TACTICAL_BUDGET)
        self.strategic = PaperBook(Book.STRATEGIC, STRATEGIC_BUDGET, STRATEGIC_BUDGET)
        self.reserve_cash = RESERVE_BUDGET
        self.tactical_policy = TacticalPolicy()
        self.strategic_policy = StrategicPolicy()

    def snapshot(self) -> dict[str, Any]:
        def book_state(book: PaperBook) -> dict[str, Any]:
            return {**asdict(book), "nav": round(book.nav, 2), "deployed": round(book.maximum_allocation - book.cash, 2)}
        snapshot = {
            "tactical": book_state(self.tactical), "strategic": book_state(self.strategic),
            "cash_treasury_reserve": self.reserve_cash,
            "total_nav": round(self.tactical.nav + self.strategic.nav + self.reserve_cash, 2),
            "authority": {"paper_mode": True, "broker_connectivity": False, "live_execution": False},
        }
        if round(snapshot["total_nav"], 2) != round(self.tactical.nav + self.strategic.nav + self.reserve_cash, 2):
            raise RuntimeError("paper fund conservation violated")
        return snapshot

    def validate_open(self, book: Book, instrument: str, notional: float, cluster: str = "UNKNOWN") -> list[str]:
        target = self.tactical if book == Book.TACTICAL else self.strategic
        policy = self.tactical_policy if book == Book.TACTICAL else self.strategic_policy
        reasons: list[str] = []
        if notional <= 0 or notional > target.cash:
            reasons.append("INSUFFICIENT_BOOK_CASH")
        if notional > target.maximum_allocation * policy.max_position_pct:
            reasons.append("POSITION_LIMIT")
        if instrument not in target.positions and len(target.positions) >= policy.max_concurrent_positions:
            reasons.append("CONCURRENT_EXPOSURE_LIMIT")
        if book == Book.TACTICAL and target.daily_realized_pnl <= -(target.maximum_allocation * policy.daily_loss_limit_pct):
            reasons.append("DAILY_LOSS_LIMIT")
        if book == Book.STRATEGIC:
            cluster_value = sum(p.market_value for p in target.positions.values() if p.correlation_cluster == cluster)
            if cluster_value + notional > target.maximum_allocation * policy.max_cluster_pct:
                reasons.append("CORRELATION_CLUSTER_LIMIT")
        return reasons

    def open_position(self, *, book: Book, instrument: str, quantity: float, reference_price: float,
                      thesis: str, invalidation: str, cluster: str = "UNKNOWN", fill_model: FillModel | None = None) -> dict[str, Any]:
        if book not in {Book.TACTICAL, Book.STRATEGIC}:
            raise ValueError("paper positions require a tactical or strategic book")
        model = fill_model or FillModel()
        filled_qty, fill_price = model.fill("BUY", quantity, reference_price)
        notional = filled_qty * fill_price
        reasons = self.validate_open(book, instrument, notional, cluster)
        if not thesis.strip() or not invalidation.strip():
            reasons.append("THESIS_AND_INVALIDATION_REQUIRED")
        if reasons:
            return {"status": "REJECTED", "reasons": sorted(set(reasons)), "paper_mode": True}
        target = self.tactical if book == Book.TACTICAL else self.strategic
        target.cash -= notional
        target.positions[instrument] = PaperPosition(instrument, filled_qty, fill_price, fill_price, thesis, invalidation, cluster)
        return {"status": "PAPER_FILLED", "book": book, "instrument": instrument, "quantity": filled_qty,
                "fill_price": fill_price, "notional": round(notional, 2), "live_execution": False}

    def classify_tactical_eod(self, session: str, classifications: dict[str, str]) -> dict[str, Any]:
        missing = sorted(set(self.tactical.positions) - set(classifications))
        if missing:
            return {"status": "INCOMPLETE", "missing_instruments": missing}
        allowed = {"CARRY", "EXIT_NEXT_SESSION", "THESIS_INVALIDATED", "MONITOR"}
        invalid = sorted(key for key, value in classifications.items() if value not in allowed)
        if invalid:
            return {"status": "INCOMPLETE", "invalid_instruments": invalid}
        receipt = {"session": session, "classifications": dict(classifications), "status": "COMPLETE"}
        self.tactical.classifications.append(receipt)
        return receipt
