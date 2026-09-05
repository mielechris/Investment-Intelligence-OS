from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT=Path(__file__).parents[3]
COMPONENT=ROOT/"FRONT END"/"src"/"ExpansionWingFactory.tsx"
STYLE=ROOT/"FRONT END"/"src"/"ExpansionWingFactory.css"


class LivingFactoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.component=COMPONENT.read_text(); cls.style=STYLE.read_text()

    def test_every_department_maps_to_structured_state(self):
        for room,source in (("Intake and Radar Dock","radar"),("Candidate Conveyor","candidate_conveyor"),
            ("Multi-Asset Trading Floor","multi_asset_factory"),("Professional Strategy Observatory","professional_strategy_observatory"),
            ("Historical Pattern Laboratory","outcomes_9j"),("Skeptic / Red Room","primary_source_review_queue"),
            ("Investment Committee Room","committee"),("Risk Inspection","risk"),("Paper Execution Bay","books"),
            ("Portfolio Office","books"),("Learning Theater","benchmark_9h"),("Evidence Warehouse","knowledge_operations")):
            self.assertIn(f'["{room}","{source}"]',self.component)

    def test_all_ten_desks_and_instrument_metaphors_are_present(self):
        for lane in ("us_equities","equity_etfs","treasury_rates","bond_proxies","commodity_proxies",
                     "fx_proxies","crypto_reference","listed_options","intraday","relative_value"):
            self.assertIn(f'["{lane}"',self.component)
        self.assertIn("lf-desk__screen",self.component)

    def test_dialogue_is_deterministic_and_does_not_invent_market_content(self):
        self.assertIn("deterministicDialogue",self.component)
        for state in ("MARKET_CLOSED_WEEKEND","PRE_MARKET","REGULAR_SESSION","AVAILABLE_EMPTY","FAILED_CLOSED","STALE"):
            self.assertIn(state,self.component)
        for prohibited in ("recommendation","price target","return forecast","buy now"):
            self.assertNotIn(prohibited,self.component.lower())

    def test_candidate_identity_is_bounded_and_lineage_failures_are_idle(self):
        self.assertIn(".slice(0,5)",self.component)
        self.assertIn("immutable candidate lineage is unavailable",self.component)
        self.assertIn("No prior identities carried forward",self.component)
        self.assertNotIn("promotion_candidate_count",self.component)

    def test_unknown_empty_and_paper_research_are_distinct(self):
        self.assertIn('candidate_count==null?"UNKNOWN"',self.component)
        self.assertIn("AVAILABLE_EMPTY",self.component)
        self.assertIn("Paper Research Lab",self.component)
        self.assertIn("operational positions",self.component.lower())
        self.assertNotIn("candidate_count||0",self.component)

    def test_authority_locks_and_no_order_controls(self):
        for marker in ("NO BROKER","NO LEDGER WRITES","NO LIVE EXECUTION","PAPER SIMULATION"):
            self.assertIn(marker,self.component)
        for prohibited in ("place order","submit order","connect broker"):
            self.assertNotIn(prohibited,self.component.lower())

    def test_audit_drawer_focus_escape_and_sanitized_sources(self):
        for marker in ('role="dialog"','aria-modal="true"','event.key==="Escape"',"requestAnimationFrame",
                       "projection_activation","projection_freshness","provider_credit_meter","authority_lock"):
            self.assertIn(marker,self.component)
        self.assertNotIn("filesystem",self.component.lower()); self.assertNotIn("credential_value",self.component)

    def test_responsive_reduced_motion_and_overflow_contracts(self):
        for marker in ("grid-template-columns:repeat(5,minmax(0,1fr))","@media(max-width:1100px)",
                       "grid-template-columns:repeat(2,minmax(0,1fr))","@media(max-width:620px)",
                       "grid-template-columns:minmax(0,1fr)","overflow:hidden","prefers-reduced-motion"):
            self.assertIn(marker,self.style)

    def test_no_raw_json_in_default_factory(self):
        self.assertEqual(self.component.count("JSON.stringify"),1)
        self.assertIn('<details className="lf-tech">',self.component)

    def test_fixture_and_live_identity_are_explicit(self):
        self.assertIn("FIXTURE / NON-LIVE",self.component); self.assertIn("LIVE READ-ONLY",self.component)

    def test_existing_sixteen_scenario_manifest_remains_complete(self):
        value=json.loads((ROOT/"BACK END"/"backend"/"expansion_wing"/"fixtures"/"tuesday_rehearsal_scenarios.json").read_text())
        self.assertEqual(value["fixture_label"],"SYNTHETIC_FIXTURE_NON_LIVE")
        self.assertEqual(len(value["scenarios"]),16)


if __name__=="__main__": unittest.main()
