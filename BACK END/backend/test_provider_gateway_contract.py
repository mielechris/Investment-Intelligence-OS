"""Synthetic provider receipt integrity tests; no native or provider execution."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from provider_gateway_contract import (
    content_hash, locked_authority, pin, readiness, readiness_matrix, safe_document, seal,
    verify_receipt, write_receipt,
)


class ContractTests(unittest.TestCase):
    def receipt(self):
        return seal({"schema": "iios-provider-receipt-v1", "provider": "MASSIVE",
                     "parents": {"request": "a" * 64}, "authority": locked_authority(),
                     "observations": [], "normalized_observation_hash": content_hash([])})

    def test_hash_is_deterministic_and_order_independent(self):
        self.assertEqual(content_hash({"a": 1, "b": 2}), content_hash({"b": 2, "a": 1}))
        with self.assertRaises(ValueError):
            content_hash({"v": float("nan")})

    def test_wrong_independent_pin_rejected(self):
        with self.assertRaises(ValueError):
            pin({"a": 1}, "f" * 64)

    def test_valid_self_hash_wrong_parent_rejected(self):
        value = self.receipt()
        with self.assertRaisesRegex(ValueError, "PARENT"):
            verify_receipt(value, content_hash(value), parents={"request": "b" * 64})

    def test_rehashed_authority_escalation_rejected(self):
        value = self.receipt()
        value["authority"]["live_execution"] = True
        value = seal({k: v for k, v in value.items() if k != "content_hash"})
        with self.assertRaisesRegex(ValueError, "AUTHORITY"):
            verify_receipt(value, content_hash(value), parents=value["parents"])

    def test_exclusive_write_and_existing_evidence_unchanged(self):
        root = Path(tempfile.mkdtemp(prefix="gateway-receipt-", dir=os.environ["IIOS_GATEWAY_TEST_ROOT"]))
        value = self.receipt()
        path = write_receipt(root, value, content_hash(value), parents=value["parents"])
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            write_receipt(root, value, content_hash(value), parents=value["parents"])
        self.assertEqual(path.read_bytes(), before)

    def test_symlink_root_rejected(self):
        root = Path(tempfile.mkdtemp(prefix="gateway-alias-", dir=os.environ["IIOS_GATEWAY_TEST_ROOT"]))
        alias = root / "alias"
        alias.symlink_to(root, target_is_directory=True)
        value = self.receipt()
        with self.assertRaises(ValueError):
            write_receipt(alias, value, content_hash(value), parents=value["parents"])

    def test_sensitive_keys_and_query_values_rejected(self):
        for value in ({"api_key": "SYNTHETIC_SENTINEL"}, {"nested": {"headers": {}}},
                      {"url": "https://example.invalid/?key=SYNTHETIC_SENTINEL"}):
            with self.subTest(value=type(value).__name__), self.assertRaises(ValueError):
                safe_document(value)

    def test_chatgpt_connector_cannot_make_readiness_green(self):
        value = readiness(bindings={"chatgpt_connected": True, "RUNTIME INTEGRATION": "GREEN"})
        self.assertEqual(value["RUNTIME INTEGRATION"], "UNVERIFIED")
        self.assertEqual(value["OVERALL READINESS"], "NOT_READY")
        self.assertNotIn("GREEN", json.dumps(value))

    def test_all_six_readiness_rows_remain_independent(self):
        value = readiness_matrix({})
        self.assertEqual(len(value["providers"]), 6)
        self.assertTrue(all(r["OVERALL READINESS"] == "NOT_READY" for r in value["providers"].values()))
