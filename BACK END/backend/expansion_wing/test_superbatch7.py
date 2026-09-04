from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from expansion_wing.investor_intelligence import (
    Claim, InterviewSession, SourceRecord, SourceRegistry, content_hash, contradictions,
    deduplicate_claims, interview_plan,
)
from expansion_wing.judgment import JudgmentPrinciple, promote_status
from expansion_wing.knowledge_pipeline import GovernedWorkQueue, PipelineLimits, room_projection
from expansion_wing.pattern_lab import PointInTimeObservation, walk_forward_test
from expansion_wing.professional_library import initial_library


def fixture_source(**changes) -> SourceRecord:
    values = dict(source_id="fixture-source", professional_id="fixture-investor", title="Fixture note",
        publisher="Fixture Publisher", author="Fixture Author", investor="Fixture Investor",
        publication_date="2025-01-01", retrieval_date="2026-09-03", source_type="ARTICLE",
        source_url="fixture://source/one", source_domain="fixture", point_in_time_available_at="2025-01-01",
        public=True, user_provided=False, permitted_use="PERMITTED", rights_review_status="PERMITTED",
        representation="PARAPHRASED", content_hash=content_hash("fixture note"),
        provenance="SYNTHETIC_FIXTURE", applicable_assets=("EQUITY",), applicable_regimes=("EXPANSION",),
        freshness="CURRENT", human_review_status="PENDING", notes="Short governed note.")
    values.update(changes)
    return SourceRecord(**values)


def fixture_claim(identifier="c1", **changes) -> Claim:
    values = dict(claim_id=identifier, source_id="fixture-source", proposition="Margins may persist",
        polarity="SUPPORTS", representation="PARAPHRASED", evidence_known_at="2025-01-01",
        attribution="Fixture Investor", evidence_location="page 1", timeframe="2025",
        risks=("competition",), counterarguments=("mean reversion",), confidence=0.4, claim_kind="OPINION")
    values.update(changes)
    return Claim(**values)


class SourceGovernanceTests(unittest.TestCase):
    def test_supported_lawful_source_classes_and_deduplication(self):
        registry = SourceRegistry()
        kinds = ("SEC_FILING", "SHAREHOLDER_LETTER", "BOOK_NOTE", "LAWFUL_EXCERPT", "ARTICLE",
                 "PUBLIC_INTERVIEW", "PODCAST", "PUBLIC_VIDEO")
        for index, kind in enumerate(kinds):
            item = fixture_source(source_id=f"s{index}", source_type=kind,
                content_hash=content_hash(f"fixture-{index}"), source_url=f"fixture://source/{index}")
            self.assertEqual(registry.register(item), "QUEUED_FOR_HUMAN_REVIEW")
        self.assertEqual(registry.register(fixture_source(source_id="duplicate",
            content_hash=content_hash("fixture-0"))), "DUPLICATE")

    def test_rights_attribution_and_copyright_fail_closed(self):
        rejected = {
            "author": "", "rights_review_status": "REVIEW_REQUIRED", "paywall_bypassed": True,
            "confidential": True, "illegally_copied": True, "complete_copyrighted_work": True,
            "limited_quotation": "x" * 281,
        }
        for field, value in rejected.items():
            with self.subTest(field=field), self.assertRaises((ValueError, PermissionError)):
                SourceRegistry().register(fixture_source(**{field: value}))
        with self.assertRaises(ValueError):
            fixture_source(source_url="https://official.example/item", source_domain="other.example").validate()

    def test_point_in_time_and_bounded_notes_required(self):
        with self.assertRaises(ValueError): fixture_source(point_in_time_available_at="not-a-date").validate()
        with self.assertRaises(ValueError): fixture_source(notes=" ").validate()


class InterviewAndClaimTests(unittest.TestCase):
    def test_consent_confidential_and_review_lifecycle(self):
        session = InterviewSession("i1", "jesse", "AUDIO", upload_size_bytes=10)
        self.assertIn("CONSENT_REQUIRED", session.intake_status()["reasons"])
        session.consent = True; session.permitted_uses = ("RESEARCH",); session.confidential_exclusion = True
        session.transcription_status = "COMPLETE"; session.transcript = "Synthetic corrected fixture."
        session.speakers = ("Jesse", "Interviewer"); session.corrected = True
        self.assertEqual(session.approval_status()["status"], "PENDING")
        session.speaker_attribution_status = "APPROVED"; session.correction_status = "APPROVED"
        session.professional_approved = True
        self.assertEqual(session.approval_status()["status"], "APPROVED")
        self.assertFalse(session.approval_status()["judgment_bank_auto_write"])

    def test_payload_and_jesse_topics_are_bounded(self):
        session = InterviewSession("i2", "jesse", "VIDEO", consent=True, permitted_uses=("RESEARCH",),
            confidential_exclusion=True, upload_size_bytes=25_000_001)
        self.assertIn("PAYLOAD_TOO_LARGE", session.intake_status()["reasons"])
        plan = interview_plan("Jesse")
        self.assertEqual(plan["theme_evidence_status"], "SOURCE_REVIEW_REQUIRED")
        self.assertIn("contemporaneous_news", plan["required_topics"])
        self.assertFalse(plan["statements_invented"])

    def test_claim_classes_duplicate_contradiction_and_private_boundaries(self):
        for kind in ("FACTUAL_OBSERVATION", "OPINION", "HEURISTIC", "CAUSAL_CLAIM", "PREDICTION"):
            fixture_claim(claim_kind=kind).validate()
        unique, duplicate_ids = deduplicate_claims([fixture_claim(), fixture_claim("c2")])
        self.assertEqual(len(unique), 1); self.assertEqual(duplicate_ids, ["c2"])
        opposite = fixture_claim("c3", polarity="CONTRADICTS")
        self.assertEqual(contradictions([fixture_claim(), opposite])[0]["status"], "HUMAN_REVIEW_REQUIRED")
        with self.assertRaises(ValueError): fixture_claim(hidden_reasoning="private chain").validate()
        with self.assertRaises(ValueError): fixture_claim(quotation="invented quotation").validate()
        with self.assertRaises(ValueError): fixture_claim(investor_position="long XYZ").validate()


class JudgmentPatternResourceTests(unittest.TestCase):
    def principle(self) -> JudgmentPrinciple:
        return JudgmentPrinciple("j1", "fixture-source", "2025-01-01", "Fixture Investor", "PARAPHRASED",
            ["EQUITY"], ["EXPANSION"], "Synthetic rule", [], "entry", "bounded", "exit", "invalidate",
            [{"fixture": True}], [{"fixture": True}], .4, {"forward_paper_validation": True}, "reviewer",
            permissions={"right_to_use": True, "confidential": False})

    def test_exact_judgment_lifecycle_and_human_gate(self):
        item = self.principle()
        with self.assertRaises(PermissionError): promote_status(item, "PROVISIONAL", human_approved=False)
        with self.assertRaises(ValueError): promote_status(item, "VALIDATED", human_approved=True)
        for state in ("PROVISIONAL", "VALIDATED", "RETIRED"):
            self.assertEqual(promote_status(item, state, human_approved=True).status, state)
        rejected = self.principle(); promote_status(rejected, "PROVISIONAL", human_approved=True)
        promote_status(rejected, "REJECTED", human_approved=True)
        self.assertEqual(promote_status(rejected, "RETIRED", human_approved=True).status, "RETIRED")

    def test_point_in_time_walk_forward_costs_and_benchmark(self):
        rows = [PointInTimeObservation(f"2025-01-0{i}T00:00:00Z", {"signal": 1}, value, "FIXTURE",
            spread_cost=.01, slippage_cost=.01, feature_observed_at={"signal": f"2025-01-0{i}T00:00:00Z"})
            for i, value in ((1, .1), (2, .1), (3, .2), (4, -.1))]
        result = walk_forward_test(rows, lambda _: True, benchmark_returns=[.01, .01])
        self.assertTrue(result["point_in_time"] and result["out_of_sample"])
        self.assertTrue(result["transaction_costs_included"] and result["failures_included"])
        self.assertFalse(result["causality_claimed"] or result["profitability_claimed"])
        future = replace(rows[-1], feature_observed_at={"signal": "2025-01-05T00:00:00Z"})
        self.assertEqual(walk_forward_test(rows[:-1] + [future], lambda _: True)["reason"], "LOOK_AHEAD_FEATURE_DETECTED")

    def test_queue_resource_and_zero_cost_fail_closed(self):
        limits = PipelineLimits(max_payload_bytes=3, max_queue_depth=1, max_concurrency=1, max_retries=1,
            timeout_seconds=2, daily_cost_ceiling=0, monthly_cost_ceiling=0)
        self.assertEqual(GovernedWorkQueue(limits).admit(b"1234")["failure_category"], "PAYLOAD_TOO_LARGE")
        self.assertEqual(GovernedWorkQueue(limits).admit(b"1", elapsed_seconds=3)["failure_category"], "TIMEOUT")
        self.assertEqual(GovernedWorkQueue(limits).admit(b"1", estimated_cost=None)["failure_category"], "COST_UNKNOWN")
        self.assertEqual(GovernedWorkQueue(limits).admit(b"1", estimated_cost=1)["failure_category"], "COST_CEILING")
        queue = GovernedWorkQueue(limits); self.assertTrue(queue.admit(b"1")["admitted"])
        self.assertEqual(queue.admit(b"1")["failure_category"], "DUPLICATE")
        self.assertEqual(queue.admit(b"2")["failure_category"], "QUEUE_FULL")
        self.assertTrue(all(value is False for value in queue.status()["authority"].values()))


class LibraryPresentationTests(unittest.TestCase):
    def test_professional_library_coverage_and_hypothesis_policy(self):
        library = initial_library(); names = {item["profile"]["display_name"] for item in library}
        required = {"Warren Buffett", "Charlie Munger", "Peter Lynch", "Howard Marks", "Stanley Druckenmiller",
            "George Soros", "Paul Tudor Jones", "Joel Greenblatt"}
        self.assertTrue(required <= names)
        specialties = {specialty for item in library for specialty in item["plan"]["specialties"]}
        self.assertTrue({"FIXED_INCOME", "TREASURY", "COMMODITY", "FUTURES", "IPO", "QUANT_FACTOR",
                         "TREND_FOLLOWING", "DISTRESSED"} <= specialties)
        self.assertTrue(all(item["opinions_are_hypotheses"] and
            item["plan"]["hypothesis_status"] == "SOURCE_REVIEW_REQUIRED" and
            item["plan"]["acquisition_status"] == "NOT_ACTIVATED" and
            not item["plan"]["external_requests_allowed"] for item in library))

    def test_truthful_empty_rooms_and_strict_count_projection(self):
        empty = room_projection()
        self.assertEqual(empty["Interview Studio"]["presentation_status"], "AVAILABLE_FOR_REVIEWED_UPLOAD")
        self.assertIsNone(empty["Investor Archive"]["data"]["source_count"])
        self.assertEqual(empty["Judgment Foundry"]["presentation_status"], "AVAILABLE_EMPTY")
        state = room_projection({"source_count": 2, "rights_review_queue_count": 2})
        self.assertEqual(state["Investor Archive"]["presentation_status"], "CURRENT")
        with self.assertRaises(ValueError): room_projection({"fabricated_return": 1})
        with self.assertRaises(ValueError): room_projection({"source_count": -1})

    def test_frontend_status_contract_and_get_head_only_preview(self):
        repo = Path(__file__).parents[3]
        context = (repo / "FRONT END/src/ExpansionWingSnapshotContext.ts").read_text()
        styles = (repo / "FRONT END/src/ExpansionWingStates.css").read_text()
        ui = (repo / "FRONT END/src/ExpansionWing.tsx").read_text()
        server = (Path(__file__).parent / "preview_server.py").read_text()
        self.assertIn('"SOURCE_REVIEW_REQUIRED"', context)
        self.assertIn("wing-state--source_review_required", styles)
        self.assertIn('AVAILABLE_FOR_REVIEWED_UPLOAD: "UPLOAD READY"', ui)
        self.assertIn('"GET", "HEAD"', server)
        self.assertIn('name.startswith("do_")', server)
        self.assertIn("METHOD_NOT_ALLOWED", server)


if __name__ == "__main__": unittest.main()
