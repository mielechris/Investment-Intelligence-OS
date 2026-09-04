from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from expansion_wing.market_session_controller import current_session_evidence, session_truth
from expansion_wing.multi_asset_factory import classify_lane_proposal
from expansion_wing.multi_asset_projection import ReadOnlyProjectionReader, build_projection, validate_projection
from expansion_wing.tuesday_rehearsal import SCENARIOS, character_commentary, rehearsal_projection, run_rehearsal

UTC=timezone.utc
TUESDAY=datetime(2026,9,8,14,0,tzinfo=UTC)


class Calendar:
    def __init__(self,status=False): self.status=status
    def holiday_status(self,_day:date): return self.status


def lanes(state="AVAILABLE_EMPTY"):
    names=("us_equities","equity_etfs","treasury_rates","bond_proxies","commodity_proxies","fx_proxies",
        "crypto_reference","listed_options","intraday","relative_value")
    return {name:{"state":state,"freshness":state,"candidate_count":0 if state=="AVAILABLE_EMPTY" else None,
        "research_eligible":False,"paper_eligible":False,"missing_evidence":"CURRENT_SESSION_EVIDENCE",
        "instrument_basis":"REFERENCE_ONLY" if name=="crypto_reference" else ("EXPLICIT_PROXY" if name in
            {"treasury_rates","bond_proxies","commodity_proxies","fx_proxies","relative_value"} else "DIRECT")}
        for name in names}


def projection(**changes):
    values=dict(source_generated_at="2026-09-08T13:59:00+00:00",source_cycle_id="fixture_cycle_1",
        projection_generated_at="2026-09-08T14:00:00+00:00",evidence_freshness_state="AVAILABLE_EMPTY",
        market_session_state="PRE_MARKET",lane_states=lanes(),candidate_conveyor={"state":"AVAILABLE_EMPTY","candidates":[]},
        professional_observatory={"state":"AVAILABLE_EMPTY","observation_count":0,"primary_verification_state":"UNAVAILABLE",
            "agreement_state":"UNAVAILABLE","sample_warning":True,"endorsement":False},
        scoreboard={"state":"INCOMPLETE","sample_size":0,"unresolved_observations":0,"hit_rate":None,
            "calibration":None,"return_distribution_state":"UNAVAILABLE","drawdown_distribution_state":"UNAVAILABLE",
            "sample_warning":True,"survivorship_warning":True},
        paper_research_sleeves={"state":"AVAILABLE_EMPTY","sleeve_count":0,"operational_position_count":0,
            "authoritative_cash":10000,"paper_authority":False,"broker_authority":False},
        provider={"state":"UNAVAILABLE","confirmed_credits":None,"ambiguous_credits":None,
            "remaining_ceiling":None,"outbound_requests":0},queue={"state":"AVAILABLE_EMPTY","depth":0},
        authoritative_paper_nav=10000,last_trustworthy_hash=None,enabled=True,validation_clock=TUESDAY)
    values.update(changes); return build_projection(**values)


class ProjectionTests(unittest.TestCase):
    def test_schema_hash_and_serialization_are_deterministic(self):
        first=projection(); second=projection(); self.assertEqual(first,second)
        self.assertEqual(first["schema_version"],"iios-multi-asset-read-only-projection-v1")
        self.assertEqual(len(first["projection_hash"]),64); validate_projection(first,now=TUESDAY)

    def test_unknown_fields_hash_tamper_and_oversize_rejected(self):
        value=projection(); value["unknown"]="x"
        with self.assertRaises(ValueError): validate_projection(value,now=TUESDAY)
        value=projection(); value["projection_hash"]="0"*64
        with self.assertRaisesRegex(ValueError,"HASH"): validate_projection(value,now=TUESDAY)
        huge=lanes(); huge["us_equities"]["missing_evidence"]="x"*70000
        with self.assertRaisesRegex(ValueError,"TOO_LARGE"): projection(lane_states=huge)

    def test_future_and_false_current_freshness_rejected(self):
        with self.assertRaisesRegex(ValueError,"LOOK_AHEAD"):
            projection(projection_generated_at="2026-09-08T14:01:00+00:00")
        with self.assertRaisesRegex(ValueError,"FRESHNESS"):
            projection(source_generated_at="2026-09-08T12:00:00+00:00",evidence_freshness_state="AVAILABLE")

    def test_absence_is_not_zero_and_failed_cycle_cannot_carry_candidates(self):
        bad=lanes(); bad["intraday"]={**bad["intraday"],"state":"UNAVAILABLE","freshness":"UNAVAILABLE","candidate_count":0}
        with self.assertRaisesRegex(ValueError,"ABSENT_INFORMATION"):
            projection(lane_states=bad)
        row={"candidate_id":"candidate_1500000000000001","instrument_id":"SYNTH1","asset_lane":"us_equities",
            "originating_scanner":"EXISTING_IIOS_519_SYMBOL_SCANNER","discovered_at":"2026-09-08T13:59:00Z",
            "source_cycle_id":"fixture_cycle_1","completeness":"INCOMPLETE","missing_fields":["company_profile"],
            "verification_state":"PRIMARY_SOURCE_REQUIRED","promotion_state":"BLOCKED","blocked_reason":"PRIMARY_SOURCE_REQUIRED"}
        with self.assertRaisesRegex(ValueError,"CARRY_FORWARD"):
            projection(candidate_conveyor={"state":"FAILED_CLOSED","candidates":[row]})

    def test_fixed_reader_disabled_and_strict(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); reader=ReadOnlyProjectionReader(root)
            with self.assertRaisesRegex(RuntimeError,"DISABLED"): reader.read()
            path=root/"multi-asset-projection.json"; path.write_text(json.dumps(projection()))
            loaded=ReadOnlyProjectionReader(root,enabled=True,validation_clock=TUESDAY).read(); self.assertEqual(loaded["projection_hash"],projection()["projection_hash"])
            path.write_text(json.dumps({**loaded,"private":"x"}))
            with self.assertRaisesRegex(RuntimeError,"UNAVAILABLE"): ReadOnlyProjectionReader(root,enabled=True,validation_clock=TUESDAY).read()

    def test_authorities_provider_keychain_broker_and_ledger_are_zero(self):
        value=projection(); self.assertEqual(value["provider"]["outbound_requests"],0)
        self.assertFalse(any(value["authority"].values())); self.assertFalse(value["paper_research_sleeves"]["paper_authority"])
        encoded=json.dumps(value); self.assertNotIn("credential_value",encoded); self.assertNotIn("filesystem_path",encoded)


class SessionTests(unittest.TestCase):
    def test_every_session_state_and_holiday_requires_approved_calendar(self):
        sunday=session_truth(datetime(2026,9,6,16,tzinfo=UTC),Calendar())
        pre=session_truth(datetime(2026,9,8,12,tzinfo=UTC),Calendar())
        regular=session_truth(datetime(2026,9,8,15,tzinfo=UTC),Calendar())
        post=session_truth(datetime(2026,9,8,21,tzinfo=UTC),Calendar())
        holiday=session_truth(datetime(2026,9,8,15,tzinfo=UTC),Calendar(True))
        unknown=session_truth(datetime(2026,9,8,15,tzinfo=UTC),Calendar(None))
        self.assertEqual({x.state for x in (sunday,pre,regular,post,holiday,unknown)},
            {"MARKET_CLOSED_WEEKEND","PRE_MARKET","REGULAR_SESSION","POST_MARKET","MARKET_CLOSED_HOLIDAY","UNKNOWN"})
        self.assertFalse(unknown.calendar_approved); self.assertTrue(regular.intraday_eligible)

    def test_prior_session_stale_future_rejected_and_missing_unavailable(self):
        session=session_truth(datetime(2026,9,8,15,tzinfo=UTC),Calendar())
        self.assertEqual(current_session_evidence(session=session,evidence_session_date=None,evidence_timestamp=None)["state"],"UNAVAILABLE")
        self.assertEqual(current_session_evidence(session=session,evidence_session_date="2026-09-07",evidence_timestamp="2026-09-07T20:00:00Z")["state"],"STALE")
        self.assertEqual(current_session_evidence(session=session,evidence_session_date="2026-09-08",evidence_timestamp="2026-09-08T16:00:00Z")["state"],"FAILED_CLOSED")

    def test_intraday_latency_and_price_freshness_fail_closed(self):
        fields={"market_session":"REGULAR","observed_at":"2026-09-08T15:00:00Z","price_timestamp":"2026-09-08T15:00:00Z",
            "latency_ms":2501,"spread":.01,"liquidity":"HIGH","market_hours_state":"OPEN"}
        self.assertEqual(classify_lane_proposal("intraday",fields,now=datetime(2026,9,8,15,tzinfo=UTC))["reason"],"INTRADAY_LATENCY_EXCESSIVE")
        fields["latency_ms"]=10; fields["price_timestamp"]="2026-09-08T14:58:00Z"
        self.assertEqual(classify_lane_proposal("intraday",fields,now=datetime(2026,9,8,15,tzinfo=UTC))["reason"],"INTRADAY_PRICE_STALE")


class RehearsalTests(unittest.TestCase):
    def test_all_sixteen_synthetic_scenarios_rehearse_without_side_effects(self):
        result=run_rehearsal(datetime(2026,9,8,15,tzinfo=UTC),Calendar())
        self.assertEqual((result["scenario_count"],set(result["scenarios"])),(16,set(SCENARIOS)))
        self.assertEqual((result["provider_requests"],result["provider_credits"],result["ledger_writes"],result["paper_positions_created"]),(0,0,0,0))
        self.assertFalse(result["keychain_access"] or result["broker_access"] or any(result["authority"].values()))
        self.assertEqual(result["scenarios"]["weekend_closed"]["market_session_state"],"MARKET_CLOSED_WEEKEND")
        self.assertEqual(result["scenarios"]["tuesday_pre_market"]["market_session_state"],"PRE_MARKET")

    def test_specialized_and_failure_scenarios_are_truthful(self):
        result=run_rehearsal(datetime(2026,9,8,15,tzinfo=UTC),Calendar())["scenarios"]
        self.assertEqual(result["options_incomplete"]["lane_states"]["listed_options"]["state"],"INCOMPLETE")
        self.assertEqual(result["bond_incomplete"]["lane_states"]["bond_proxies"]["state"],"INCOMPLETE")
        self.assertEqual(result["intraday_stale"]["lane_states"]["intraday"]["state"],"STALE")
        self.assertEqual(result["professional_only_blocked"]["candidate_conveyor"]["state"],"AVAILABLE_EMPTY")
        self.assertEqual(result["complete_failure"]["candidate_conveyor"],{"state":"FAILED_CLOSED","candidates":[]})
        self.assertIsNone(result["complete_failure"]["lane_states"]["intraday"]["candidate_count"])

    def test_character_commentary_uses_only_structured_state(self):
        value=rehearsal_projection(datetime(2026,9,8,15,tzinfo=UTC),Calendar(),scenario="complete_failure")
        lines=character_commentary(value); self.assertIn("failed closed",lines["factory"].lower())
        self.assertNotIn("SYNTH1",json.dumps(lines)); self.assertEqual(lines["structured_state_only"],"true")

    def test_fixture_manifest_is_explicitly_non_live(self):
        path=Path(__file__).parent/"fixtures/tuesday_rehearsal_scenarios.json"; value=json.loads(path.read_text())
        self.assertEqual(value["fixture_label"],"SYNTHETIC_FIXTURE_NON_LIVE"); self.assertEqual(len(value["scenarios"]),16)
        self.assertFalse(value["credentials"] or value["private_9i_evidence"] or value["live_opportunities_claimed"])


if __name__=="__main__": unittest.main()
