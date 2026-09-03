from __future__ import annotations

from typing import Any

from .models import Book, Eligibility
from .opportunities import create_passport
from .portfolio import DualBookPortfolio, TOTAL_BUDGET
from .projection import build_living_wall_projection


class ExpansionWingEngine:
    def __init__(self, paper_fund_read_model: dict[str, Any]) -> None:
        if paper_fund_read_model.get("fixture_label") not in {None, "SYNTHETIC_FIXTURE_NON_LIVE"}:
            raise ValueError("unrecognized fixture label")
        source_total = float(paper_fund_read_model.get("total_nav") or 0)
        if round(source_total, 2) != TOTAL_BUDGET:
            raise ValueError("paper fund must reconcile to exactly $10,000")
        self.portfolio = DualBookPortfolio()
        self.passports: dict[str, Any] = {}

    def ingest_opportunity(self, payload: dict[str, Any]) -> dict[str, Any]:
        passport = create_passport(payload)
        self.passports[passport.passport_id] = passport
        return passport.to_dict()

    def request_paper_simulation(self, passport_id: str, *, quantity: float, reference_price: float,
                                 thesis: str, invalidation: str, valuation: dict[str, Any] | None = None) -> dict[str, Any]:
        passport = self.passports.get(passport_id)
        if passport is None:
            return {"status": "REJECTED", "reasons": ["UNKNOWN_PASSPORT"]}
        if passport.eligibility != Eligibility.ELIGIBLE or passport.applicable_book == Book.OBSERVATION_ONLY:
            return {"status": "REJECTED", "reasons": ["PASSPORT_NOT_PAPER_ELIGIBLE"], "paper_mode": True}
        return self.portfolio.open_position(book=passport.applicable_book, instrument=passport.instrument,
                                            quantity=quantity, reference_price=reference_price, thesis=thesis,
                                            invalidation=invalidation, valuation=valuation,
                                            cluster=str(passport.correlation.get("cluster") or "UNKNOWN"))

    def fixture_projection(self, sources: dict[str, Any]) -> dict[str, Any]:
        sources = dict(sources)
        sources["books"] = {"observed_at": sources.get("last_cycle", {}).get("observed_at"), "complete": True,
                            "data": self.portfolio.snapshot() | {"fixture_label": "SYNTHETIC_FIXTURE_NON_LIVE"}}
        sources["radar"] = {"observed_at": sources.get("last_cycle", {}).get("observed_at"), "complete": True,
                            "data": {"passports": [row.to_dict() for row in self.passports.values()],
                                     "fixture_label": "SYNTHETIC_FIXTURE_NON_LIVE"}}
        projection = build_living_wall_projection(sources)
        projection["mode"] = "FIXTURE_NON_LIVE"
        return projection
