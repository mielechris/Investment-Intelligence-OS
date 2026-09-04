from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from expansion_wing import acceptance_server
from expansion_wing.multi_asset_factory import (
    ASSET_CLASSES, AUTHORITY, CommonOpportunityPassport, ProfessionalObservation,
    browser_projection, build_scoreboard, classify_lane_proposal, fuse_candidate,
    lane_registry, professional_source_registry,
)
from expansion_wing.paper_research_lab import ParallelPaperLaboratory, ResearchSleeveObservation

NOW=datetime(2026,9,8,20,0,tzinfo=timezone.utc)


def passport(**changes):
    values=dict(opportunity_id="opp_0123456789abcdef0123",source_timestamp="2026-09-03T19:00:00Z",
        effective_timestamp="2026-09-03T19:01:00Z",asset_class="US_EQUITY",instrument_type="COMMON_STOCK",
        instrument_id="MU",direction="LONG",strategy_family="QUALITY_VALUE",time_horizon="12_MONTHS",
        catalyst="reviewed catalyst",thesis="reported hypothesis",counter_thesis="reviewed countercase",
        expected_return_range=(-.1,.2),maximum_modeled_loss=.2,liquidity_classification="HIGH",
        volatility_classification="MEDIUM",correlation_cluster="SEMIS",invalidation_conditions=("condition",),
        evidence_freshness="CURRENT",evidence_completeness="COMPLETE",primary_source_verification_state="VERIFIED",
        professional_research_observations=("pro_1",),scanner_observations=("scan_1",),
        historical_analog_results=("hist_1",),confidence=.5,governance_status="PRIMARY_REVIEW_REQUIRED")
    values.update(changes); return CommonOpportunityPassport(**values)


def observation(**changes):
    values=dict(observation_id="pro_0123456789abcdef",professional_id="fixture_manager",source_type="SEC_13F",
        publication_timestamp="2026-09-01T12:00:00Z",observation_timestamp="2026-09-02T12:00:00Z",
        asset_class="US_EQUITY",themes=("semiconductors",),stated_thesis="reported opinion",
        observed_positioning="reported holding",valuation_framework="UNKNOWN",catalyst="UNKNOWN",horizon="UNKNOWN",
        risks=("disclosure delay",),invalidation=("position changed",),conviction="UNSUPPORTED",
        words_positioning_agreement="UNKNOWN",primary_evidence_reference="official-record-hash",
        rights_status="PUBLIC_OFFICIAL")
    values.update(changes); return ProfessionalObservation(**values)


def sleeve(lane="us_equities"):
    return ResearchSleeveObservation("sleeve_1",lane,"2026-09-08T19:00:00Z","FIXTURE_QUOTE",10,1,5,
        "equal weight","invalidation","close rule","5D","DAILY","SIMPLE_BENCHMARK",1000)


class MultiAssetContractTests(unittest.TestCase):
    def test_passport_and_browser_projection_are_bounded(self):
        item=passport(); item.validate(now=NOW); safe=item.browser_safe()
        self.assertNotIn("thesis",safe); self.assertEqual(safe["professional_research_observation_count"],1)
        self.assertTrue(all(value is False for value in safe["authority"].values()))

    def test_lookahead_unknown_asset_identifier_and_implicit_authority_rejected(self):
        invalid=(passport(effective_timestamp="2026-09-09T00:00:00Z"),passport(asset_class="UNKNOWN"),
            passport(instrument_id="bad symbol"),passport(authority={**AUTHORITY,"broker":True}))
        for item in invalid:
            with self.assertRaises(ValueError): item.validate(now=NOW)

    def test_unverified_candidate_cannot_be_paper_eligible(self):
        with self.assertRaisesRegex(ValueError,"PRIMARY_SOURCE_REQUIRED"):
            passport(governance_status="PAPER_ELIGIBLE",primary_source_verification_state="PENDING").validate(now=NOW)

    def test_all_ten_independent_lanes_registered(self):
        lanes=lane_registry(); self.assertEqual(len(lanes),10); self.assertEqual({x.asset_class for x in lanes},ASSET_CLASSES)
        self.assertEqual(len({x.lane_id for x in lanes}),10)

    def test_proxy_is_never_underlying(self):
        result=classify_lane_proposal("commodity_proxies",{"proxy_basis":"LIQUID_COMMODITY_ETF","roll_effect":"KNOWN"})
        self.assertEqual((result["state"],result["reason"]),("RESEARCH_ONLY","PROXY_NOT_UNDERLYING"))

    def test_missing_options_and_bond_fields_fail_closed(self):
        self.assertEqual(classify_lane_proposal("listed_options",{})["reason"],"RESEARCH_ONLY_UNPRICEABLE")
        self.assertEqual(classify_lane_proposal("bond_proxies",{})["reason"],"REQUIRED_INSTRUMENT_FIELDS_MISSING")

    def test_market_closed_intraday_and_unsupported_lane(self):
        fields={key:"FIXTURE" for key in next(x for x in lane_registry() if x.lane_id=="intraday").required_fields}
        self.assertEqual(classify_lane_proposal("intraday",fields,market_open=False)["reason"],"MARKET_CLOSED")
        self.assertEqual(classify_lane_proposal("other",{})["state"],"FAILED_CLOSED")


class ProfessionalAndFusionTests(unittest.TestCase):
    def test_professional_observation_is_attributed_hypothesis_with_delay(self):
        item=observation(); item.validate(now=NOW); result=item.research_question()
        self.assertEqual(result["state"],"ATTRIBUTED_HYPOTHESIS"); self.assertEqual(result["disclosure_delay_seconds"],86400)
        self.assertFalse(any(result["authority"].values()))

    def test_stale_or_future_professional_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError,"LOOK_AHEAD_REJECTED"):
            observation(publication_timestamp="2026-09-03T00:00:00Z",observation_timestamp="2026-09-02T00:00:00Z").validate(now=NOW)

    def test_registry_preserves_market_vision_and_koyfin_boundaries(self):
        sources={x["source_type"]:x for x in professional_source_registry()}
        self.assertEqual(sources["MARKET_VISION"]["trust"],"SECONDARY_DOMAIN_EXPERT")
        self.assertTrue(sources["KOYFIN_MANUAL_IMPORT"]["human_cockpit_only"])

    def test_scoreboard_warns_on_sample_and_never_endorses(self):
        board=build_scoreboard((observation(later_accuracy_score=.75),))
        self.assertTrue(board["sample_size_warning"]); self.assertFalse(board["investment_endorsement"])
        self.assertEqual(board["observations_evaluated"],1)

    def test_professional_opinion_alone_cannot_promote(self):
        row={"source_type":"PROFESSIONAL_OBSERVATION","source_id":"pro1","timestamp":"2026-09-08T19:00:00Z","signal":"UP","correlation_cluster":"SEMIS"}
        result=fuse_candidate((row,)); self.assertEqual(result["state"],"INCOMPLETE")
        self.assertFalse(result["professional_opinion_sufficient"]); self.assertFalse(any(result["authority"].values()))

    def test_fusion_preserves_agreement_contradiction_and_duplicates(self):
        rows=tuple({"source_type":kind,"source_id":kind,"timestamp":"2026-09-08T19:00:00Z",
            "signal":"UP" if kind!="HISTORICAL_PATTERN" else "DOWN","correlation_cluster":"SEMIS"}
            for kind in ("IIOS_SCANNER","PROFESSIONAL_OBSERVATION","HISTORICAL_PATTERN"))
        result=fuse_candidate(rows+(rows[0],)); self.assertEqual(result["state"],"PRIMARY_REVIEW_REQUIRED")
        self.assertEqual((result["contradictions"],result["correlated_duplicates"]),(1,1))


class PaperAndVisualTests(unittest.TestCase):
    def test_independent_sleeves_do_not_create_positions(self):
        lab=ParallelPaperLaboratory(); result=lab.add(sleeve(),{"price":100,"liquidity":"HIGH"})
        self.assertEqual(result["state"],"RESEARCH_RECORDED"); snap=lab.snapshot()
        self.assertEqual((snap["consolidated_paper_nav"],snap["actual_paper_positions_created"]),(10000,0))
        self.assertFalse(any(snap["authority"].values()))

    def test_sleeve_rejects_more_than_consolidated_nav(self):
        with self.assertRaises(ValueError): replace(sleeve(),modeled_notional=10001).validate({"price":1,"liquidity":"HIGH"})

    def test_unpriceable_option_is_not_recorded(self):
        lab=ParallelPaperLaboratory(); result=lab.add(sleeve("listed_options"),{})
        self.assertEqual(result["reason"],"RESEARCH_ONLY_UNPRICEABLE"); self.assertEqual(lab.snapshot()["research_sleeve_count"],0)

    def test_browser_projection_truth_and_fixed_nav(self):
        lanes={x.lane_id:"AVAILABLE_EMPTY" for x in lane_registry()}; board=build_scoreboard(())
        value=browser_projection(lane_states=lanes,professional_count=0,scoreboard=board,sleeve_count=0,
            consolidated_nav=10000,candidate_state="AVAILABLE_EMPTY")
        self.assertEqual(value["provider_status"],"NOT_ACTIVATED"); self.assertFalse(any(value["authority"].values()))
        with self.assertRaises(ValueError): browser_projection(lane_states=lanes,professional_count=0,
            scoreboard=board,sleeve_count=0,consolidated_nav=10001,candidate_state="AVAILABLE_EMPTY")

    def test_compositor_rejects_unsafe_projection_and_accepts_empty(self):
        lanes={x.lane_id:"AVAILABLE_EMPTY" for x in lane_registry()}; board=build_scoreboard(())
        value=browser_projection(lane_states=lanes,professional_count=0,scoreboard=board,sleeve_count=0,
            consolidated_nav=10000,candidate_state="AVAILABLE_EMPTY")
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); missing=[root/f"missing-{i}" for i in range(4)]
            compositor=acceptance_server.Compositor(*missing,"http://127.0.0.1:8002/system/status",multi_asset_reader=lambda:value)
            compositor._reachability=lambda:"CURRENT"; snapshot=compositor.snapshot()
            self.assertEqual(snapshot["sections"]["multi_asset_factory"]["state"],"AVAILABLE_EMPTY")
            unsafe={**value,"authority":{**AUTHORITY,"broker":True}}
            compositor.multi_asset_reader=lambda:unsafe
            self.assertEqual(compositor.snapshot()["sections"]["multi_asset_factory"]["state"],"UNAVAILABLE")
            leaked={**value,"scoreboard":{**value["scoreboard"],"private_evidence":{"text":"hidden"}}}
            compositor.multi_asset_reader=lambda:leaked
            self.assertEqual(compositor.snapshot()["sections"]["multi_asset_factory"]["state"],"UNAVAILABLE")


if __name__ == "__main__": unittest.main()
