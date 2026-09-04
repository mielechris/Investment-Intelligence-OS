from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .multi_asset_factory import AUTHORITY, classify_lane_proposal, lane_registry

TOTAL_PAPER_NAV = 10_000.0


@dataclass(frozen=True)
class ResearchSleeveObservation:
    sleeve_id: str
    lane_id: str
    modeled_entry_timestamp: str
    modeled_entry_price_source: str
    slippage_bps: float
    fees: float
    spread_bps: float
    sizing_hypothesis: str
    stop_or_invalidation: str
    exit_rules: str
    holding_period: str
    mark_frequency: str
    benchmark: str
    modeled_notional: float
    realized_result: float | None = None
    unrealized_result: float | None = None
    maximum_favorable_excursion: float | None = None
    maximum_adverse_excursion: float | None = None
    outcome_attribution: str = "UNRESOLVED"

    def validate(self, instrument_fields: dict[str, Any], *, market_open: bool = True) -> dict[str,Any]:
        lane={x.lane_id:x for x in lane_registry()}.get(self.lane_id)
        if lane is None or self.modeled_notional < 0 or self.modeled_notional > TOTAL_PAPER_NAV or min(self.slippage_bps,self.fees,self.spread_bps)<0:
            raise ValueError("RESEARCH_SLEEVE_INVALID")
        if not all((self.sleeve_id,self.modeled_entry_timestamp,self.modeled_entry_price_source,
                    self.sizing_hypothesis,self.stop_or_invalidation,self.exit_rules,self.holding_period,
                    self.mark_frequency,self.benchmark)):
            raise ValueError("RESEARCH_SLEEVE_INVALID")
        return classify_lane_proposal(self.lane_id,instrument_fields,market_open=market_open)


class ParallelPaperLaboratory:
    """In-memory research scoring only; it has no portfolio, ledger, order, or broker dependency."""
    def __init__(self) -> None:
        self._sleeves: dict[str,ResearchSleeveObservation]={}

    def add(self, observation: ResearchSleeveObservation, instrument_fields: dict[str,Any], *, market_open: bool=True) -> dict[str,Any]:
        classification=observation.validate(instrument_fields,market_open=market_open)
        if classification["state"] in {"INCOMPLETE","FAILED_CLOSED"}: return classification
        if observation.sleeve_id in self._sleeves: return {"state":"DUPLICATE","authority":AUTHORITY.copy()}
        self._sleeves[observation.sleeve_id]=observation
        return {"state":"RESEARCH_RECORDED","paper_position_created":False,"authority":AUTHORITY.copy()}

    def snapshot(self) -> dict[str,Any]:
        return {"equal_weight_research_scoreboard":True,"research_sleeve_count":len(self._sleeves),
            "modeled_notional_total":sum(x.modeled_notional for x in self._sleeves.values()),
            "consolidated_paper_nav":TOTAL_PAPER_NAV,"actual_paper_positions_created":0,
            "sleeves":[{"sleeve_id":x.sleeve_id,"lane_id":x.lane_id,"outcome_attribution":x.outcome_attribution} for x in self._sleeves.values()],
            "authority":AUTHORITY.copy()}
