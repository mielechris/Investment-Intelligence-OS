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


class SerializationEquivalenceTests(unittest.TestCase):
    @staticmethod
    def original(value):
        # Frozen pre-optimization implementation, including recursive order.
        import re
        from provider_gateway_contract import DENIED_KEYS, canonical
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str) or key.lower() in DENIED_KEYS:
                    raise ValueError('SENSITIVE_DOCUMENT_REJECTED')
                SerializationEquivalenceTests.original(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                SerializationEquivalenceTests.original(child)
        elif isinstance(value, str):
            if re.search(r'(?i)(bearer\s|api[_-]?key[=:]|password[=:]|[?&](token|key)=|-----BEGIN .*PRIVATE KEY)', value):
                raise ValueError('SENSITIVE_DOCUMENT_REJECTED')
        elif value is not None and type(value) not in (int, float, bool):
            raise ValueError('PUBLIC_JSON_REQUIRED')
        canonical(value)

    def outcome(self, fn, value):
        from provider_gateway_contract import canonical, content_hash
        try:
            result=fn(value)
            return ('accepted',result,canonical(value),content_hash(value))
        except Exception as error:
            return ('rejected',type(error),error.args)

    def test_valid_and_adversarial_match_original(self):
        class Text(str):pass
        class Sequence(list):pass
        cases=[None,True,False,0,-0.0,1.5,2**256,'μ\\\"\n',(),[],{},
               {'a':['MU']*2000,'b':(True,None,17,1.5)},Sequence(['MU','MU']),Text('MU'),
               float('nan'),float('inf'),float('-inf'),object(),b'bytes',
               {1:'x'},{'API_KEY':'SYNTHETIC'},{'a':[None,{'password':'SYNTHETIC'}]},
               'bearer SYNTHETIC','api_key=SYNTHETIC','\ud800',
               {'a':float('nan'),'password':'SYNTHETIC'},
               {'password':'SYNTHETIC','a':float('nan')},10**5000]
        for i,value in enumerate(cases):
            with self.subTest(case=i):self.assertEqual(self.outcome(self.original,value),self.outcome(safe_document,value))

    def test_repetition_changes_no_bytes_or_hashes(self):
        for size in (0,1,100,1500):
            value={'items':[{'symbol':'MU','i':i,'flags':[False,None,0,-0.0]} for i in range(size)]}
            self.assertEqual(self.outcome(self.original,value),self.outcome(safe_document,value))

    def test_no_approval_cached_between_calls_or_mutations(self):
        value={'a':['MU']*20};safe_document(value)
        value['a'].append({'authorization':'SYNTHETIC'})
        self.assertEqual(self.outcome(self.original,value),self.outcome(safe_document,value))
        with self.assertRaises(ValueError):safe_document(value)

    def test_bounded_primitive_serialization_reuse_and_container_checks(self):
        from unittest.mock import patch
        import provider_gateway_contract as contract
        encoder=contract.canonical
        value=['MU']*100
        with patch.object(contract,'canonical',wraps=encoder) as calls:
            safe_document(value)
            self.assertEqual(calls.call_count,2)  # One scalar, one full container.
            safe_document(value)
            self.assertEqual(calls.call_count,4)  # No cross-call cache.
        values=list(range(1100))+[1099]*3
        with patch.object(contract,'canonical',wraps=encoder) as calls:
            safe_document(values)
            self.assertEqual(calls.call_count,1104)  # Cache bound, no skipped container.

    def test_cycles_still_reject(self):
        value=[];value.append(value)
        for fn in (self.original,safe_document):
            with self.assertRaises(RecursionError):fn(value)
