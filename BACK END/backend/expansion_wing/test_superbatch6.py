from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from expansion_wing.investor_intelligence import (AcquisitionQueue, AcquisitionRequest, Claim, InterviewSession,
    ProfessionalProfile, SourceRecord, SourceRegistry, classify_rights, content_hash, contradictions,
    interview_plan, judgment_handoff, normalize_content, pattern_handoff, review_packet)
from expansion_wing.preview_server import HOST, PreviewApplication, handler_for
from http.server import ThreadingHTTPServer


class FakeCompositor:
    def __init__(self, state="CURRENT"): self.calls = 0; self.state = state
    def snapshot(self):
        self.calls += 1
        return {"sections": {"service_health": {"state": self.state}, "shadow_9i": {"state": "UNAVAILABLE",
            "data": {"reason": "BROWSER_SUMMARY_NOT_AVAILABLE"}}}}


class FailingCompositor:
    def snapshot(self): raise RuntimeError("private path and source value")


class PreviewServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        (self.root / "index.html").write_text("EXPANSION_APP"); (self.root / "asset.js").write_text("SAFE")
        self.compositor = FakeCompositor(); self.app = PreviewApplication(self.root, self.compositor)
    def tearDown(self): self.temp.cleanup()

    def test_static_confinement_and_limits(self):
        self.assertEqual(self.app.static_file("/"), (self.root / "index.html").resolve())
        self.assertEqual(self.app.static_file("/asset.js"), (self.root / "asset.js").resolve())
        self.assertIsNone(self.app.static_file("/../private")); self.assertIsNone(self.app.static_file("/%2e%2e/private"))
        (self.root / "large").write_bytes(b"x" * 2_000_001); self.assertIsNone(self.app.static_file("/large"))

    def test_cache_is_bounded_and_single_refresh(self):
        first = self.app.snapshot(now=10); second = self.app.snapshot(now=20)
        self.assertIs(first, second); self.assertEqual(self.compositor.calls, 1)
        self.app.snapshot(now=26); self.assertEqual(self.compositor.calls, 2)

    def test_health_allowlist_and_missing_9i(self):
        health = self.app.health()
        self.assertEqual(set(health), {"service_status", "schema_version", "snapshot_truth_state", "generated_at",
            "source_availability_categories", "backend_reachability_category", "read_only", "ledger_write",
            "trade_execution_permission", "broker_connected", "live_execution"})
        self.assertTrue(health["read_only"]); self.assertFalse(any(health[key] for key in
            ("ledger_write", "trade_execution_permission", "broker_connected", "live_execution")))
        self.assertEqual(self.app.snapshot()["sections"]["shadow_9i"]["data"]["reason"], "BROWSER_SUMMARY_NOT_AVAILABLE")

    def test_loopback_get_only_headers_and_graceful_shutdown(self):
        server = ThreadingHTTPServer((HOST, 0), handler_for(self.app)); self.assertEqual(server.server_address[0], HOST)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        base = f"http://{HOST}:{server.server_address[1]}"
        try:
            with urlopen(base + "/health", timeout=2) as response:
                self.assertEqual(response.status, 200); self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                self.assertTrue(json.load(response)["read_only"])
            with self.assertRaises(HTTPError) as rejected:
                urlopen(Request(base + "/snapshot", method="POST"), timeout=2)
            self.assertEqual(rejected.exception.code, 405)
            rejected.exception.close()
            with self.assertRaises(HTTPError) as missing: urlopen(base + "/../private", timeout=2)
            self.assertEqual(missing.exception.code, 404)
            missing.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_startup_missing_source_is_truthfully_unavailable(self):
        app = PreviewApplication(self.root, FakeCompositor("UNAVAILABLE"))
        self.assertEqual(app.health()["snapshot_truth_state"], "UNAVAILABLE")

    def test_runtime_failure_is_fixed_and_sanitized(self):
        server = ThreadingHTTPServer((HOST, 0), handler_for(PreviewApplication(self.root, FailingCompositor())))
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            with self.assertRaises(HTTPError) as failure:
                urlopen(f"http://{HOST}:{server.server_address[1]}/snapshot", timeout=2)
            body = failure.exception.read().decode(); failure.exception.close()
            self.assertEqual(failure.exception.code, 503); self.assertEqual(body, '{"status":"SERVICE_UNAVAILABLE"}')
            self.assertNotIn("private", body)
        finally: server.shutdown(); server.server_close(); thread.join(2)

    def test_duplicate_instance_refusal_contract(self):
        source = (Path(__file__).parent / "preview_server.py").read_text()
        self.assertIn("LOCK_NB", source); self.assertIn("DUPLICATE_INSTANCE", source)
        self.assertNotIn("latest_" + "shadow_counterfactual.json", source)

    def test_install_and_exact_rollback_contracts(self):
        repo = Path(__file__).parents[3]
        install = (repo / "scripts/install_expansion_wing_preview.sh").read_text()
        uninstall = (repo / "scripts/uninstall_expansion_wing_preview.sh").read_text()
        plist = (repo / "config/com.iios.expansion-wing-preview.plist.template").read_text()
        for marker in ("com.iios.expansion-wing-preview", "127.0.0.1", "5177", "expansion_wing.preview_server"):
            self.assertIn(marker, install + plist)
        self.assertIn("WORKTREE_NOT_CLEAN", install); self.assertIn("PORT_IN_USE", install)
        self.assertIn('gui/$(id -u)/$label', uninstall)
        self.assertNotIn("sudo", install + uninstall); self.assertNotIn("launchctl kickstart", install + uninstall)


def source(source_id="s1", text="permitted note"):
    return SourceRecord(source_id, "p1", "Title", "Publisher", "2025-01-01", "2026-09-03", "ARTICLE",
        True, False, "PERMITTED", "PERMITTED", "PARAPHRASED", content_hash(text), "PUBLIC_ATTRIBUTABLE",
        ("EQUITY",), ("EXPANSION",), "CURRENT", "PENDING")


class InvestorIntelligenceTests(unittest.TestCase):
    def test_registry_rights_and_hash_deduplication(self):
        registry = SourceRegistry(); self.assertEqual(registry.register(source()), "QUEUED_FOR_HUMAN_REVIEW")
        self.assertEqual(registry.register(source("s2")), "DUPLICATE")
        blocked = source("bad"); blocked = SourceRecord(**{**blocked.__dict__, "permitted_use": "PROHIBITED"})
        with self.assertRaises(PermissionError): registry.register(blocked)
        self.assertEqual(classify_rights(public=True, user_provided=False, licensed=False, paywalled=False,
                                         complete_copyrighted_work=False), "REVIEW_REQUIRED")
        self.assertEqual(classify_rights(public=True, user_provided=False, licensed=False, paywalled=True,
                                         complete_copyrighted_work=False), "PROHIBITED")

    def test_normalization_and_copyright_boundary(self):
        value = normalize_content("  a  permitted   paraphrase ", source_type="ARTICLE", rights="PERMITTED", quotation="short")
        self.assertEqual(value["normalized_text"], "a permitted paraphrase"); self.assertFalse(value["complete_copyrighted_work_stored"])
        with self.assertRaises(ValueError): normalize_content("text", source_type="BOOK_NOTE", rights="PERMITTED", quotation="x" * 281)
        with self.assertRaises(PermissionError): normalize_content("text", source_type="ARTICLE", rights="REVIEW_REQUIRED")

    def test_zero_cost_queue_is_not_activated(self):
        queue = AcquisitionQueue(daily_cost_ceiling=0)
        self.assertEqual(queue.enqueue(AcquisitionRequest("s", 1, 0)), "QUEUED_NOT_ACTIVATED")
        self.assertEqual(queue.enqueue(AcquisitionRequest("s", 1, 0)), "DUPLICATE")
        self.assertEqual(queue.enqueue(AcquisitionRequest("paid", 1, 1)), "REJECTED_COST_CEILING")
        self.assertEqual(queue.snapshot()["status"], "NOT_ACTIVATED")

    def test_claim_contradiction_review_and_handoffs(self):
        profile = ProfessionalProfile("p1", "Professional", "INVESTOR", ("VALUE_QUALITY",))
        claims = [Claim("c1", "s1", "Debt is low", "SUPPORTS", "PARAPHRASED", "2025-01-01"),
                  Claim("c2", "s2", "Debt is low", "CONTRADICTS", "DIRECT", "2025-01-02")]
        self.assertEqual(len(contradictions(claims)), 1)
        packet = review_packet(profile, source(), claims); self.assertTrue(packet["human_approval_required"])
        self.assertEqual(judgment_handoff(packet, human_approved=False)["status"], "BLOCKED_HUMAN_APPROVAL")
        self.assertEqual(pattern_handoff(packet, human_approved=True, point_in_time_locked=False)["status"], "BLOCKED")
        self.assertFalse(pattern_handoff(packet, human_approved=True, point_in_time_locked=True)["future_information_allowed"])

    def test_interview_consent_correction_and_professional_approval(self):
        interview = InterviewSession("i1", "jesse", "TEXT")
        self.assertFalse(interview.intake_status()["processing_authorized"])
        interview.consent = True; interview.permitted_uses = ("RESEARCH",); interview.confidential_exclusion = True
        interview.transcript = "corrected attributable transcript"; interview.speakers = ("Jesse",); interview.corrected = True
        self.assertEqual(interview.approval_status()["status"], "PENDING")
        interview.professional_approved = True; self.assertEqual(interview.approval_status()["status"], "APPROVED")
        self.assertFalse(interview.approval_status()["judgment_bank_auto_write"])
        plan = interview_plan("Jesse"); self.assertEqual(plan["orchestrator"], "MAX")
        self.assertEqual(plan["theme_evidence_status"], "SOURCE_REVIEW_REQUIRED"); self.assertFalse(plan["statements_invented"])


if __name__ == "__main__": unittest.main()
