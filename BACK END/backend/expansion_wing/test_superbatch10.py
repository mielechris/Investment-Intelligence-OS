from __future__ import annotations

import json
import secrets
import unittest

from expansion_wing.encrypted_archive import FixtureAuthenticatedCipher
from expansion_wing.keychain_adapter import CommandResult, KeychainAdapter
from expansion_wing.operational_aead import (AES256_GCM_KAT, CryptographyAESGCMBackend, OperationalAEAD,
    dependency_status, known_answer_check, reject_fixture_cipher_for_operations)
from expansion_wing.reviewer_auth import Authenticator, Reviewer, ReviewerRegistry, separated_duties
from expansion_wing.review_service import ReviewServiceContract
from expansion_wing.scanner_adapters import ScannerResult, accept_scan
from expansion_wing.sec_compliance import MockableSECThrottle, SECContactConfig
from expansion_wing.security_readiness import FIELDS, browser_security_readiness


class MappingBackend:
    def __init__(self): self.values = {}
    def encrypt(self, key, nonce, plaintext, aad):
        value = b"mock-aead:" + plaintext; self.values[(key, nonce, value, aad)] = plaintext; return value
    def decrypt(self, key, nonce, ciphertext, aad):
        try: return self.values[(key, nonce, ciphertext, aad)]
        except KeyError: raise RuntimeError("AEAD_AUTHENTICATION_FAILED") from None


class KnownAnswerBackend:
    def encrypt(self, key, nonce, plaintext, aad):
        assert (key, nonce, plaintext, aad) == tuple(AES256_GCM_KAT[key] for key in ("key", "nonce", "plaintext", "aad"))
        return AES256_GCM_KAT["ciphertext_and_tag"]
    def decrypt(self, key, nonce, ciphertext, aad):
        assert ciphertext == AES256_GCM_KAT["ciphertext_and_tag"]; return AES256_GCM_KAT["plaintext"]


class AEADContractTests(unittest.TestCase):
    def test_dependency_is_fail_closed_and_known_answer_contract(self):
        self.assertIn(dependency_status(), {"NOT_AVAILABLE", "AVAILABLE_FOR_REVIEW"})
        if dependency_status() == "NOT_AVAILABLE":
            with self.assertRaises(RuntimeError): CryptographyAESGCMBackend()
        self.assertTrue(known_answer_check(KnownAnswerBackend()))

    def test_round_trip_authenticated_metadata_tamper_and_downgrade(self):
        adapter = OperationalAEAD(MappingBackend()); key = secrets.token_bytes(32); nonce = secrets.token_bytes(12)
        encoded = adapter.seal(b"synthetic", key, key_id="fixture-key",
            metadata={"record_type": "note", "created_at": "2026-09-03", "content_hash": "a" * 64}, nonce=nonce)
        self.assertEqual(adapter.open(encoded, key), b"synthetic")
        tampered = json.loads(encoded); tampered["metadata"]["record_type"] = "claim"
        with self.assertRaises(RuntimeError): adapter.open(json.dumps(tampered).encode(), key)
        downgraded = json.loads(encoded); downgraded["algorithm"] = "FIXTURE-HMAC-SHA256-ETM-V1"
        with self.assertRaisesRegex(RuntimeError, "DOWNGRADE"): adapter.open(json.dumps(downgraded).encode(), key)

    def test_nonce_reuse_bounds_and_fixture_operational_rejection(self):
        adapter = OperationalAEAD(MappingBackend()); key = secrets.token_bytes(32)
        kwargs = dict(key_id="k", metadata={"record_type": "note"}, nonce=secrets.token_bytes(12))
        adapter.seal(b"one", key, **kwargs)
        with self.assertRaisesRegex(RuntimeError, "NONCE_REUSE"): adapter.seal(b"two", key, **kwargs)
        with self.assertRaises(ValueError): adapter.seal(b"", key, key_id="k", metadata={})
        with self.assertRaisesRegex(RuntimeError, "FIXTURE_CIPHER"): reject_fixture_cipher_for_operations(FixtureAuthenticatedCipher())


class KeychainTests(unittest.TestCase):
    class Runner:
        def __init__(self, results): self.results = iter(results); self.calls = []
        def run(self, argv, *, stdin, environment):
            self.calls.append((argv, stdin, environment)); return next(self.results)

    def test_mocked_create_retrieve_rotate_delete_never_puts_secret_in_args_or_env(self):
        secret = secrets.token_bytes(32); rotated_secret = secrets.token_bytes(32)
        runner = self.Runner([CommandResult(0), CommandResult(0, secret),
            CommandResult(0, secret), CommandResult(0), CommandResult(0)])
        adapter = KeychainAdapter(runner, service="com.iios.fixture")
        self.assertEqual(adapter.create("k1", secret), "CREATED"); self.assertEqual(adapter.retrieve("k1"), secret)
        self.assertEqual(adapter.rotate("k1", "k2", rotated_secret, recovery_verified=True), "ROTATION_STAGED")
        self.assertEqual(adapter.delete("k1", human_authorized=True), "DELETED")
        for argv, stdin, environment in runner.calls:
            self.assertNotIn(secret, [item.encode() for item in argv]); self.assertEqual(environment, {})
        self.assertEqual(runner.calls[0][1], secret)

    def test_duplicate_missing_ambiguous_lost_key_and_unauthorized_delete(self):
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE"):
            KeychainAdapter(self.Runner([CommandResult(45)]), service="s").create("k", secrets.token_bytes(32))
        with self.assertRaisesRegex(RuntimeError, "MISSING"):
            KeychainAdapter(self.Runner([CommandResult(44)]), service="s").retrieve("k")
        with self.assertRaisesRegex(RuntimeError, "AMBIGUOUS"):
            KeychainAdapter(self.Runner([CommandResult(0, b"short")]), service="s").retrieve("k")
        with self.assertRaises(PermissionError):
            KeychainAdapter(self.Runner([]), service="s").delete("k", human_authorized=False)


class AuthenticationServiceTests(unittest.TestCase):
    def setup_auth(self, now=100.0):
        registry = ReviewerRegistry("owner"); registry.add("owner", Reviewer("rights", frozenset({"RIGHTS_REVIEWER"})))
        return registry, Authenticator(secrets.token_bytes(32), clock=lambda: now, ttl_seconds=10)

    def test_authenticated_identity_authorization_csrf_replay_and_role(self):
        registry, auth = self.setup_auth(); token = auth.session("rights")
        self.assertEqual(auth.authorize(registry, token, action="RIGHTS", csrf="c" * 32,
            idempotency_key="i" * 16, request_size=100), "rights")
        with self.assertRaises(PermissionError): auth.authorize(registry, token, action="RIGHTS", csrf="c" * 32,
            idempotency_key="j" * 16, request_size=100)
        with self.assertRaises(PermissionError): auth.authorize(registry, token, action="CLAIM", csrf="d" * 32,
            idempotency_key="k" * 16, request_size=100)
        with self.assertRaises(ValueError): auth.authorize(registry, token, action="RIGHTS", csrf="e" * 32,
            idempotency_key="l" * 16, request_size=64_001)

    def test_expiry_idempotency_rate_limit_and_separated_duties(self):
        registry = ReviewerRegistry("owner"); registry.add("owner", Reviewer("r", frozenset({"RIGHTS_REVIEWER"})))
        current = [100.0]; auth = Authenticator(secrets.token_bytes(32), clock=lambda: current[0], ttl_seconds=10); token = auth.session("r")
        current[0] = 110.0
        with self.assertRaisesRegex(PermissionError, "EXPIRED"): auth.authenticate(token)
        with self.assertRaises(PermissionError): separated_duties("same", "same")
        current[0] = 200.0; live = Authenticator(secrets.token_bytes(32), clock=lambda: current[0], ttl_seconds=60); token = live.session("r")
        live.authorize(registry, token, action="RIGHTS", csrf="a" * 32, idempotency_key="same-key-1234567", request_size=1)
        with self.assertRaisesRegex(PermissionError, "IDEMPOTENCY"):
            live.authorize(registry, token, action="RIGHTS", csrf="b" * 32, idempotency_key="same-key-1234567", request_size=1)
        limited = Authenticator(secrets.token_bytes(32), clock=lambda: 300.0, ttl_seconds=60); limited_token = limited.session("r")
        for index in range(10):
            limited.authorize(registry, limited_token, action="RIGHTS", csrf=f"{index:032d}",
                idempotency_key=f"request-{index:016d}", request_size=1)
        with self.assertRaisesRegex(RuntimeError, "RATE_LIMITED"):
            limited.authorize(registry, limited_token, action="RIGHTS", csrf="z" * 32,
                idempotency_key="final-request-0000", request_size=1)

    def test_review_service_disabled_loopback_schema_methods_and_no_trade_routes(self):
        disabled = ReviewServiceContract()
        with self.assertRaisesRegex(RuntimeError, "DISABLED"): disabled.startup("127.0.0.1")
        service = ReviewServiceContract(enabled=True, authentication_ready=True, operational_security_ready=True)
        self.assertEqual(service.startup("127.0.0.1"), "READY_FOR_REVIEW")
        with self.assertRaisesRegex(RuntimeError, "LOOPBACK"): service.startup("0.0.0.0")
        self.assertEqual(service.validate_request("GET", {})["status"], 405)
        valid = {"action": "RIGHTS", "case_id": "c", "decision": "APPROVED", "reason": "fixture",
            "csrf": "c" * 32, "idempotency_key": "i" * 16}
        self.assertEqual(service.validate_request("POST", valid)["status"], 202)
        self.assertFalse(any(word in " ".join(service.routes()) for word in ("ledger", "broker", "trade", "threshold")))


class ScannerSECProjectionTests(unittest.TestCase):
    def test_scanner_exact_clean_and_all_failure_states(self):
        clean = ScannerResult("CLEAN", "fixture-scanner", "1", 1, 1, 100)
        self.assertEqual(accept_scan(clean), "ACCEPTED_CLEAN")
        for outcome in ("UNAVAILABLE", "STALE_SIGNATURES", "TIMEOUT", "ERROR", "AMBIGUOUS", "MALWARE_DETECTED"):
            self.assertTrue(accept_scan(ScannerResult(outcome, "fixture", "1", 1, 1, 100)).startswith("REJECTED_"))
        self.assertEqual(accept_scan(ScannerResult("CLEAN", "fixture", "1", 25, 1, 100)), "REJECTED_STALE_SIGNATURES")
        self.assertEqual(accept_scan(ScannerResult("CLEAN", "fixture", "1", 1, 31, 100)), "REJECTED_TIMEOUT")

    def test_sec_configuration_and_terminal_403_429_are_mocked(self):
        with self.assertRaises(RuntimeError): SECContactConfig("", "", False).user_agent()
        for status in (403, 429):
            calls = []; gate = MockableSECThrottle(SECContactConfig("Fixture", "review@example.invalid", True),
                clock=lambda: 0, sleeper=lambda _: None)
            self.assertEqual(gate.request(lambda _ua: calls.append(status) or status), "ACCESS_POLICY_REJECTED")
            self.assertEqual(calls, [status])

    def test_browser_security_projection_is_scalar_and_rejects_secrets(self):
        values = {field: "DISABLED" for field in FIELDS}; values["operational_aead"] = "NOT_AVAILABLE"
        result = browser_security_readiness(values); encoded = json.dumps(result)
        self.assertFalse(result["secrets_exposed"] or result["identities_exposed"] or result["paths_exposed"])
        for prohibited in ("key_material", "/Users/", "reviewer_id", "ciphertext"):
            self.assertNotIn(prohibited, encoded)
        with self.assertRaises(ValueError): browser_security_readiness({**values, "keychain": "SECRET"})


if __name__ == "__main__": unittest.main()
