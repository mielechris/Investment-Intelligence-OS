from __future__ import annotations

import json
import os
import secrets
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from expansion_wing.acceptance_server import Compositor
from expansion_wing.acquisition_readiness import OfficialCandidate, disabled_acquisition_projection
from expansion_wing.knowledge_operations import knowledge_operations_projection, validate_browser_projection
from expansion_wing.review_portal import ROUTES, ReviewPortalConfig, ReviewPortalContract
from expansion_wing.reviewer_auth import Authenticator, GENESIS_HASH, LocalOwnerCeremony, ReviewerRegistry


class KnowledgeProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.security = self.root / "security"; self.archive = self.root / "archive"
        for path in (self.security, self.archive, self.archive / "manifests", self.archive / "records",
                     self.archive / "reviewers"):
            path.mkdir(mode=0o700); path.chmod(0o700)
        manifest = {"schema_version":"expansion-wing-security-manifest-v1","algorithm":"AES-256-GCM",
            "key_id":"archive-key-v1","plaintext_retained":False,"review_service_enabled":False}
        for path, payload in ((self.archive/"manifests/security.json", json.dumps(manifest).encode()),
            (self.archive/"manifests/backup.json", b"{}"), (self.archive/"records/synthetic-canary.enc", b"ciphertext"),
            (self.archive/"reviewers/owner-admin.enc", b"ciphertext")):
            path.write_bytes(payload); path.chmod(0o600)

    def tearDown(self): self.temp.cleanup()

    def test_ready_empty_projection_reads_no_encrypted_content(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("PRIVATE_READ")):
            value = knowledge_operations_projection(self.security, self.archive)
        validate_browser_projection(value)
        self.assertEqual(value["operational_encryption"], "READY")
        self.assertEqual(value["archive"], "AVAILABLE_EMPTY")
        self.assertEqual(value["review_service"], "DISABLED")
        self.assertEqual(value["public_source_intake"], "AWAITING_APPROVED_SOURCE")
        self.assertEqual(value["transcription"], "NOT_ACTIVATED")
        self.assertTrue(all(value[key] == 0 for key in value if key.endswith("_count")))

    def test_encrypted_counts_are_metadata_only_and_strict(self):
        for layer in ("original", "notes", "claims"):
            directory=self.archive/layer; directory.mkdir(mode=0o700); directory.chmod(0o700)
            item=directory/"opaque.enc"; item.write_bytes(b"never-read"); item.chmod(0o600)
        value=knowledge_operations_projection(self.security,self.archive)
        self.assertEqual((value["source_count"],value["note_count"],value["claim_count"]),(1,1,1))
        self.assertEqual(value["archive"],"READY")

    def test_malformed_manifest_modes_symlinks_and_private_fields_fail_closed(self):
        manifest=self.archive/"manifests/security.json"
        manifest.write_text(json.dumps({"schema_version":"expansion-wing-security-manifest-v1","secret":"x"})); manifest.chmod(0o600)
        self.assertEqual(knowledge_operations_projection(self.security,self.archive)["operational_encryption"],"UNAVAILABLE")
        value=knowledge_operations_projection(self.root/"missing",self.archive); self.assertFalse(value["private_data_exposed"])
        value["identity"]="private"
        with self.assertRaises(ValueError): validate_browser_projection(value)


class ReviewPortalTests(unittest.TestCase):
    def setUp(self):
        nonce=secrets.token_hex(32); self.registry=ReviewerRegistry()
        self.registry.bootstrap(LocalOwnerCeremony("501","501",True,nonce,nonce),reviewer_id="opaque-owner")
        self.auth=Authenticator(secrets.token_bytes(32),clock=lambda:100.0,ttl_seconds=60)
        self.portal=ReviewPortalContract(ReviewPortalConfig(enabled=True,port=5197),self.registry,self.auth)

    def body(self):
        return {"session":self.auth.session("opaque-owner"),"csrf":secrets.token_hex(32),
            "idempotency_key":secrets.token_hex(16),"reason":"fixture reviewed","timestamp":"2026-09-03T00:00:00Z",
            "previous_hash":self.auth.audit_events[-1]["event_hash"] if self.auth.audit_events else GENESIS_HASH}

    def test_disabled_loopback_port_and_exact_route_boundary(self):
        disabled=ReviewPortalContract(ReviewPortalConfig(port=5197),self.registry,self.auth)
        self.assertEqual(disabled.dispatch("POST","/review/rights",self.body(),encoded_size=100)["error"],"REVIEW_PORTAL_DISABLED")
        for invalid in (ReviewPortalConfig(host="0.0.0.0",port=5197),ReviewPortalConfig(port=5177)):
            with self.assertRaises(ValueError): invalid.validate()
        self.assertEqual(set(ROUTES),{"/review/rights","/review/transcript","/review/claim","/review/contradiction","/review/judgment","/review/pattern"})
        self.assertFalse(any(word in " ".join(ROUTES) for word in ("ledger","broker","trade","threshold","provider","credential","service","deploy")))

    def test_owner_authentication_csrf_replay_idempotency_and_body_limit(self):
        first=self.portal.dispatch("POST","/review/rights",self.body(),encoded_size=100); self.assertEqual(first["status"],202)
        replay=self.body(); replay["csrf"]=next(iter(self.auth.used_csrf))
        self.assertEqual(self.portal.dispatch("POST","/review/rights",replay,encoded_size=100)["error"],"CSRF_OR_REPLAY_REJECTED")
        self.assertEqual(self.portal.dispatch("GET","/review/rights",{},encoded_size=0)["status"],405)
        self.assertEqual(self.portal.dispatch("POST","/review/rights",self.body(),encoded_size=64_001)["status"],400)
        self.assertEqual(self.portal.dispatch("POST","/review/ledger",self.body(),encoded_size=100)["status"],404)

    def test_all_six_review_routes_are_owner_authorized(self):
        for route in ROUTES:
            self.assertEqual(self.portal.dispatch("POST",route,self.body(),encoded_size=100)["status"],202)


class IntegrationTruthTests(unittest.TestCase):
    def test_compositor_connects_truthful_empty_rooms(self):
        with tempfile.TemporaryDirectory() as temp:
            missing=Path(temp)/"missing"
            projection={"schema_version":"expansion-wing-knowledge-operations-v1","generated_at":"2026-09-03T00:00:00Z",
                "operational_encryption":"READY","keychain":"READY","backup_recovery":"READY","owner_reviewer":"READY",
                "review_service":"DISABLED","archive":"AVAILABLE_EMPTY","public_source_intake":"AWAITING_APPROVED_SOURCE",
                "transcription":"NOT_ACTIVATED","source_count":0,"note_count":0,"claim_count":0,
                "rights_review_queue_count":0,"transcript_review_queue_count":0,"contradiction_queue_count":0,
                "judgment_queue_count":0,"pattern_queue_count":0,"private_data_exposed":False,"authority_granted":False}
            compositor=Compositor(missing,missing,missing,missing,"http://127.0.0.1:1",lambda:projection)
            compositor._reachability=lambda:"UNAVAILABLE"; snapshot=compositor.snapshot(); rooms=snapshot["room_states"]
        self.assertEqual(rooms["Investor Archive"]["presentation_status"],"AVAILABLE_EMPTY")
        self.assertEqual(rooms["Interview Studio"]["presentation_status"],"NOT_ACTIVATED")
        self.assertEqual(rooms["Learning Theater"]["presentation_status"],"READY")
        self.assertEqual(rooms["Resource Governor"]["data"]["cost_usd"],0)
        encoded=json.dumps(snapshot)
        for prohibited in ("owner-opaque","archive-key-v1","/Users/","ciphertext","session_token","source_text","transcript_text"):
            self.assertNotIn(prohibited,encoded)

    def test_disabled_first_acquisition_queue(self):
        value=disabled_acquisition_projection(); self.assertEqual(value["status"],"AWAITING_APPROVED_SOURCE")
        self.assertFalse(value["scheduled"] or value["network_enabled"] or value["provider_enabled"] or value["authority_granted"])
        with self.assertRaises(ValueError): disabled_acquisition_projection((OfficialCandidate("x","OFFICIAL","example.com",rights_state="APPROVED"),))

    def test_frontend_one_polling_owner_and_status_accessibility(self):
        root=Path(__file__).parents[3]/"FRONT END/src"
        provider=(root/"ExpansionWingSnapshotProvider.tsx").read_text(); ui=(root/"ExpansionWing.tsx").read_text(); css=(root/"ExpansionWingStates.css").read_text()
        self.assertEqual(provider.count("fetch("),1); self.assertEqual(provider.count("setTimeout("),1)
        for path in root.glob("ExpansionWing*.tsx"):
            if path.name!="ExpansionWingSnapshotProvider.tsx": self.assertNotIn("fetch(",path.read_text())
        for value in ("READY","DISABLED","AWAITING_APPROVED_SOURCE"): self.assertIn(value,(root/"ExpansionWingSnapshotContext.ts").read_text())
        self.assertIn('title: "Resource Governor"',ui)
        for selector in ("wing-state--ready","wing-state--disabled","wing-state--awaiting_approved_source"): self.assertIn(selector,css)


if __name__ == "__main__": unittest.main()
