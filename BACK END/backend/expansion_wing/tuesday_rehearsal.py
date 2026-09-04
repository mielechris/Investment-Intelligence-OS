from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .market_session_controller import ApprovedCalendar, current_session_evidence, session_truth
from .multi_asset_factory import build_scoreboard, fuse_candidate, lane_registry
from .multi_asset_projection import AUTHORITY, build_projection

SCENARIOS=("weekend_closed","tuesday_pre_market","regular_zero_candidates","regular_immutable_candidates",
    "mixed_lane_availability","unverified_professional_observation","professional_only_blocked","stale_source",
    "provider_failed_scanner_healthy","provider_healthy_scanner_failed","options_incomplete","bond_incomplete",
    "intraday_stale","engine_disagreement","research_sleeves_only","complete_failure")


def _lane(state: str, *, count: int|None=None, basis: str="DIRECT", missing: str="NONE") -> dict[str,Any]:
    return {"state":state,"freshness":state,"candidate_count":count,"research_eligible":state=="AVAILABLE",
        "paper_eligible":False,"missing_evidence":missing,"instrument_basis":basis}


def rehearsal_projection(clock: datetime, calendar: ApprovedCalendar, *, scenario: str) -> dict[str,Any]:
    if scenario not in SCENARIOS: raise ValueError("REHEARSAL_SCENARIO_INVALID")
    session=session_truth(clock,calendar)
    lane_states={item.lane_id:_lane("AVAILABLE_EMPTY",count=0,
        basis="DIRECT" if item.direct_instrument else ("REFERENCE_ONLY" if item.lane_id=="crypto_reference" else "EXPLICIT_PROXY"))
        for item in lane_registry()}
    conveyor_state="AVAILABLE_EMPTY"; candidates=[]; provider_state="UNAVAILABLE"; evidence_state="AVAILABLE_EMPTY"
    source_cycle="fixture_cycle_tuesday_001" if scenario not in {"complete_failure","provider_healthy_scanner_failed"} else None
    if scenario=="regular_immutable_candidates":
        conveyor_state="AVAILABLE"; lane_states["us_equities"]=_lane("AVAILABLE",count=1)
        candidates=[{"candidate_id":"candidate_1500000000000001","instrument_id":"SYNTH1","asset_lane":"us_equities",
            "originating_scanner":"EXISTING_IIOS_519_SYMBOL_SCANNER","discovered_at":clock.isoformat(),
            "source_cycle_id":source_cycle,"completeness":"INCOMPLETE","missing_fields":["company_profile"],
            "verification_state":"PRIMARY_SOURCE_REQUIRED","promotion_state":"BLOCKED","blocked_reason":"PRIMARY_SOURCE_REQUIRED"}]
    elif scenario in {"complete_failure","provider_healthy_scanner_failed"}:
        conveyor_state="FAILED_CLOSED"; evidence_state="FAILED_CLOSED"
        if scenario=="complete_failure":
            lane_states={name:_lane("FAILED_CLOSED",count=None,basis=value["instrument_basis"],
                missing="SYSTEM_FAILURE") for name,value in lane_states.items()}
    elif scenario=="stale_source":
        conveyor_state="STALE"; evidence_state="STALE"
    if scenario=="mixed_lane_availability":
        lane_states["us_equities"]=_lane("AVAILABLE",count=0)
        lane_states["listed_options"]=_lane("INCOMPLETE",missing="GREEKS_AND_CONTRACT_FIELDS")
        lane_states["intraday"]=_lane("UNAVAILABLE",count=None,missing="CURRENT_SESSION_PRICE")
    if scenario=="options_incomplete": lane_states["listed_options"]=_lane("INCOMPLETE",missing="GREEKS_AND_CONTRACT_FIELDS")
    if scenario=="bond_incomplete": lane_states["bond_proxies"]=_lane("INCOMPLETE",basis="EXPLICIT_PROXY",missing="MATURITY_DURATION_PROXY_BASIS")
    if scenario=="intraday_stale": lane_states["intraday"]=_lane("STALE",count=None,missing="LATENCY_OR_PRICE_FRESHNESS")
    if scenario=="provider_failed_scanner_healthy": provider_state="FAILED_CLOSED"
    elif scenario in {"provider_healthy_scanner_failed","regular_immutable_candidates"}: provider_state="AVAILABLE"
    professional_count=1 if scenario in {"unverified_professional_observation","professional_only_blocked","engine_disagreement"} else 0
    board=build_scoreboard(())
    scoreboard={"state":"INCOMPLETE","sample_size":board["observations_evaluated"],
        "unresolved_observations":board["unresolved_observations"],"hit_rate":board["hit_rate"],
        "calibration":board["calibration"],"return_distribution_state":board["return_distribution"],
        "drawdown_distribution_state":board["drawdown_distribution"],"sample_warning":board["sample_size_warning"],
        "survivorship_warning":board["survivorship_bias_warning"]}
    projection=build_projection(source_generated_at=clock.isoformat(),source_cycle_id=source_cycle,
        projection_generated_at=clock.isoformat(),evidence_freshness_state=evidence_state,
        market_session_state=session.state,lane_states=lane_states,candidate_conveyor={"state":conveyor_state,"candidates":candidates},
        professional_observatory={"state":"INCOMPLETE" if professional_count else "AVAILABLE_EMPTY",
            "observation_count":professional_count,"primary_verification_state":"PENDING" if professional_count else "UNAVAILABLE",
            "agreement_state":"CONTRADICTION" if scenario=="engine_disagreement" else "UNAVAILABLE",
            "sample_warning":True,"endorsement":False},scoreboard=scoreboard,
        paper_research_sleeves={"state":"AVAILABLE" if scenario in {"research_sleeves_only","regular_immutable_candidates"} else "AVAILABLE_EMPTY",
            "sleeve_count":1 if scenario in {"research_sleeves_only","regular_immutable_candidates"} else 0,
            "operational_position_count":0,"authoritative_cash":10000,"paper_authority":False,"broker_authority":False},
        provider={"state":provider_state,"confirmed_credits":None,"ambiguous_credits":None,
            "remaining_ceiling":None,"outbound_requests":0},queue={"state":"AVAILABLE_EMPTY","depth":0},
        authoritative_paper_nav=10000,last_trustworthy_hash=None,enabled=True,validation_clock=clock)
    return projection


def run_rehearsal(clock: datetime, calendar: ApprovedCalendar) -> dict[str,Any]:
    sunday=clock-timedelta(days=(clock.weekday()-6)%7)
    scenario_clocks={"weekend_closed":sunday.replace(hour=12,minute=0,second=0,microsecond=0),
        "tuesday_pre_market":clock.replace(hour=8,minute=0,second=0,microsecond=0)}
    results={name:rehearsal_projection(scenario_clocks.get(name,clock.replace(hour=15,minute=0,second=0,microsecond=0)),
        calendar,scenario=name) for name in SCENARIOS}
    return {"schema_version":"iios-tuesday-rehearsal-v1","fixture_label":"SYNTHETIC_FIXTURE_NON_LIVE",
        "scenario_count":len(results),"scenarios":results,"provider_requests":0,"provider_credits":0,
        "keychain_access":False,"broker_access":False,"ledger_writes":0,"paper_positions_created":0,
        "authority":AUTHORITY.copy()}


def character_commentary(projection: dict[str,Any]) -> dict[str,str]:
    session=projection["market_session_state"]; conveyor=projection["candidate_conveyor"]["state"]
    max_line={"MARKET_CLOSED_WEEKEND":"Markets are closed for the expected weekend; IIOS is preserving the last trustworthy timestamp.",
        "PRE_MARKET":"Tuesday is pre-market; IIOS is waiting for fresh current-session evidence.",
        "REGULAR_SESSION":"The regular session is open; each lane must prove current-session evidence independently."}.get(session,"Session evidence is unavailable or outside regular hours.")
    factory_line={"AVAILABLE_EMPTY":"The scanner completed with no immutable candidates; zero is an observed result.",
        "AVAILABLE":"Immutable candidates are waiting for independent evidence and primary review.",
        "INCOMPLETE":"Candidate evidence is incomplete and cannot advance.","STALE":"Candidate evidence is stale and cannot represent the current session.",
        "FAILED_CLOSED":"The scanner failed closed; no historical candidates were substituted.",
        "UNAVAILABLE":"Exact candidate lineage is unavailable; no identities are inferred."}.get(conveyor,"Candidate state is unavailable.")
    return {"max":max_line,"factory":factory_line,"structured_state_only":"true"}
