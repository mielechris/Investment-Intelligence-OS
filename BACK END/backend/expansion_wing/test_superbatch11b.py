from __future__ import annotations

import json
import secrets
import unittest

from expansion_wing.reviewer_auth import (ACTIONS, FORBIDDEN_AUTHORITIES, GENESIS_HASH, OWNER,
    ACTION_ROLE, Authenticator, LocalOwnerCeremony, Reviewer, ReviewerRegistry)

STAMP = "2026-09-04T00:00:00Z"


def ceremony(nonce="n" * 32, *, local="501", presented="501", browser=False, controlled=True):
    return LocalOwnerCeremony(local, presented, controlled, nonce, nonce, browser)


class BootstrapTests(unittest.TestCase):
    def test_empty_registry_bootstraps_exactly_one_owner_then_permanently_closes(self):
        registry = ReviewerRegistry(); owner = registry.bootstrap(ceremony(), reviewer_id="opaque-owner")
        self.assertEqual(owner.roles, frozenset({OWNER})); self.assertEqual(len(registry.reviewers), 1)
        for retry in (ceremony(), ceremony("x" * 32)):
            with self.assertRaisesRegex(PermissionError, "PERMANENTLY_CLOSED"):
                registry.bootstrap(retry, reviewer_id="second-owner")

    def test_local_identity_storage_nonce_and_browser_boundaries(self):
        invalid = (ceremony(presented="502"), ceremony(browser=True), ceremony(controlled=False),
            LocalOwnerCeremony("501", "501", True, "short", "short"))
        for value in invalid:
            with self.assertRaisesRegex(PermissionError, "LOCAL_OWNER_CEREMONY_REQUIRED"):
                ReviewerRegistry().bootstrap(value, reviewer_id="owner")

    def test_duplicate_and_ambiguous_owner_states_fail_closed(self):
        registry = ReviewerRegistry(); registry.reviewers["existing"] = Reviewer("existing", frozenset({OWNER}))
        with self.assertRaisesRegex(PermissionError, "PERMANENTLY_CLOSED"):
            registry.bootstrap(ceremony(), reviewer_id="owner")
        registry.reviewers["second"] = Reviewer("second", frozenset({OWNER}))
        with self.assertRaisesRegex(RuntimeError, "AMBIGUOUS"):
            registry._owner("existing")


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.registry = ReviewerRegistry(); self.registry.bootstrap(ceremony(), reviewer_id="opaque-owner")
        self.now = [100.0]; self.auth = Authenticator(secrets.token_bytes(32), clock=lambda: self.now[0], ttl_seconds=60)

    def kwargs(self, index, previous=None):
        return dict(csrf=f"csrf-{index:027d}", idempotency_key=f"request-{index:016d}", request_size=64,
            reason="reviewed fixture decision", timestamp=STAMP,
            previous_hash=previous or (self.auth.audit_events[-1]["event_hash"] if self.auth.audit_events else GENESIS_HASH))

    def add_specialist(self, reviewer_id, role, index=1):
        reviewer, _ = self.auth.administer_reviewers(self.registry, self.auth.session("opaque-owner"),
            operation="ADD", reviewer_id=reviewer_id, roles=frozenset({role}),
            csrf=f"admin-{index:027d}", idempotency_key=f"admin-request-{index:012d}",
            reason="assign bounded review role", timestamp=STAMP,
            previous_hash=self.auth.audit_events[-1]["event_hash"] if self.auth.audit_events else GENESIS_HASH)
        return reviewer

    def test_owner_admin_authorized_for_exact_six_action_matrix(self):
        token = self.auth.session("opaque-owner")
        for index, action in enumerate(ACTIONS):
            extra = ({"audit_context": {"operation": "ADD", "reviewer_id": "opaque-target",
                "roles": ["RIGHTS_REVIEWER"]}} if action == "ADMINISTER_REVIEWERS" else {})
            event = self.auth.authorize(self.registry, token, action=action, **self.kwargs(index), **extra)
            self.assertTrue(event["knowledge_review_only"]); self.assertEqual(event["action"], action)
        self.assertEqual(set(ACTIONS), {"RIGHTS", "TRANSCRIPT", "CLAIM", "JUDGMENT", "PATTERN", "ADMINISTER_REVIEWERS"})

    def test_specialists_only_receive_their_exact_action(self):
        for index, (action, role) in enumerate(ACTION_ROLE.items(), 1):
            reviewer_id = f"specialist-{index}"; self.add_specialist(reviewer_id, role, index)
            token = self.auth.session(reviewer_id)
            event = self.auth.authorize(self.registry, token, action=action, **self.kwargs(index + 20))
            self.assertEqual(event["reviewer_id"], reviewer_id)
            denied = next(value for value in ACTIONS if value != action)
            with self.assertRaisesRegex(PermissionError, "ACTION_NOT_AUTHORIZED"):
                self.auth.authorize(self.registry, token, action=denied, **self.kwargs(index + 40))

    def test_authenticated_owner_only_administration_and_escalation_rejection(self):
        self.add_specialist("rights", "RIGHTS_REVIEWER")
        with self.assertRaisesRegex(PermissionError, "AUTHENTICATED_ADMINISTRATION_REQUIRED"):
            self.registry._administer(object(), "opaque-owner", operation="ADD", reviewer_id="bypass",
                roles=frozenset({"CLAIM_REVIEWER"}))
        with self.assertRaisesRegex(PermissionError, "OWNER_ADMIN_REQUIRED"):
            self.auth.administer_reviewers(self.registry, self.auth.session("rights"), operation="ADD",
                reviewer_id="claim", roles=frozenset({"CLAIM_REVIEWER"}), csrf="x" * 32,
                idempotency_key="specialist-admin-01", reason="invalid escalation", timestamp=STAMP,
                previous_hash=self.auth.audit_events[-1]["event_hash"])
        with self.assertRaisesRegex(PermissionError, "SELF_PRIVILEGE"):
            self.auth.administer_reviewers(self.registry, self.auth.session("opaque-owner"), operation="CHANGE",
                reviewer_id="opaque-owner", roles=frozenset({OWNER}), csrf="y" * 32,
                idempotency_key="owner-self-change1", reason="invalid self change", timestamp=STAMP,
                previous_hash=self.auth.audit_events[-1]["event_hash"])
        with self.assertRaisesRegex(PermissionError, "PRIVILEGE_ESCALATION"):
            self.auth.administer_reviewers(self.registry, self.auth.session("opaque-owner"), operation="CHANGE",
                reviewer_id="rights", roles=frozenset({OWNER}), csrf="z" * 32,
                idempotency_key="owner-role-change1", reason="invalid owner grant", timestamp=STAMP,
                previous_hash=self.auth.audit_events[-1]["event_hash"])

    def test_disabled_reviewer_expiration_csrf_idempotency_and_rate_limit(self):
        self.add_specialist("rights", "RIGHTS_REVIEWER"); owner_token = self.auth.session("opaque-owner")
        _, disabled = self.auth.administer_reviewers(self.registry, owner_token, operation="DISABLE",
            reviewer_id="rights", roles=frozenset(), csrf="disable" * 5, idempotency_key="disable-reviewer1",
            reason="fixture disable", timestamp=STAMP, previous_hash=self.auth.audit_events[-1]["event_hash"])
        token = self.auth.session("rights")
        with self.assertRaisesRegex(PermissionError, "INACTIVE"):
            self.auth.authorize(self.registry, token, action="RIGHTS", **self.kwargs(50, disabled["event_hash"]))
        self.now[0] = 160
        with self.assertRaisesRegex(PermissionError, "EXPIRED"): self.auth.authenticate(owner_token)
        current = [200.0]; auth = Authenticator(secrets.token_bytes(32), clock=lambda: current[0], ttl_seconds=60)
        token = auth.session("opaque-owner")
        def values(index): return dict(csrf=f"rate-{index:027d}", idempotency_key=f"rate-request-{index:012d}",
            request_size=1, reason="bounded review", timestamp=STAMP,
            previous_hash=auth.audit_events[-1]["event_hash"] if auth.audit_events else GENESIS_HASH)
        first = auth.authorize(self.registry, token, action="RIGHTS", **values(0))
        with self.assertRaisesRegex(PermissionError, "CSRF"):
            auth.authorize(self.registry, token, action="RIGHTS", **{**values(1), "csrf": "rate-000000000000000000000000000"})
        with self.assertRaisesRegex(PermissionError, "IDEMPOTENCY"):
            auth.authorize(self.registry, token, action="RIGHTS", **{**values(2), "idempotency_key": first["idempotency_key"]})
        for index in range(1, 10): auth.authorize(self.registry, token, action="RIGHTS", **values(index + 2))
        with self.assertRaisesRegex(RuntimeError, "RATE_LIMITED"):
            auth.authorize(self.registry, token, action="RIGHTS", **values(99))

    def test_audit_chain_reason_timestamp_and_sanitized_browser_boundary(self):
        token = self.auth.session("opaque-owner")
        first = self.auth.authorize(self.registry, token, action="RIGHTS", **self.kwargs(1))
        second = self.auth.authorize(self.registry, token, action="CLAIM", **self.kwargs(2, first["event_hash"]))
        self.assertEqual(second["previous_hash"], first["event_hash"])
        with self.assertRaisesRegex(ValueError, "AUDIT_CHAIN_INVALID"):
            self.auth.authorize(self.registry, token, action="PATTERN", **self.kwargs(3, GENESIS_HASH))
        with self.assertRaisesRegex(ValueError, "AUDIT_REASON_REQUIRED"):
            self.auth.authorize(self.registry, token, action="PATTERN", **{**self.kwargs(4), "reason": ""})
        serialized = json.dumps(self.auth.audit_events)
        for prohibited in ("session", "csrf", "secret", "local_identity", "/Users/"):
            self.assertNotIn(prohibited, serialized)

    def test_no_operational_authority_exists(self):
        permissions = {OWNER: set(ACTIONS), **{role: {action} for action, role in ACTION_ROLE.items()}}
        flattened = {value.upper() for values in permissions.values() for value in values}
        self.assertTrue(flattened.isdisjoint(FORBIDDEN_AUTHORITIES))
        for forbidden in ("TRADE", "LEDGER_WRITE", "BROKER", "PROVIDER", "SERVICE", "DEPLOY"):
            self.assertNotIn(forbidden, ACTIONS)


if __name__ == "__main__": unittest.main()
