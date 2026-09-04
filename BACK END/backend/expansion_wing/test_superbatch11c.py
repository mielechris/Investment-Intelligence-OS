from __future__ import annotations

import os
import base64
import subprocess
import sys
import unittest
from unittest.mock import Mock

from expansion_wing.keychain_adapter import (
    ERR_ITEM_NOT_FOUND, ERR_PARAM, KeychainAdapter, SecurityCommandRunner, SecurityFrameworkAPI,
)


class SecItemContractTests(unittest.TestCase):
    def test_exact_selector_bytes_and_err_sec_param_category(self):
        api = Mock()
        api.find.return_value = (ERR_PARAM, ())
        adapter = KeychainAdapter(api, service="diagnostic.service")
        with self.assertRaisesRegex(RuntimeError, "^INVALID_KEYCHAIN_QUERY$"):
            adapter.retrieve("diagnostic-account")
        api.find.assert_called_once_with(b"diagnostic.service", b"diagnostic-account")
        for selector in ("", "has space", "nonascii-\N{SNOWMAN}"):
            with self.assertRaises(ValueError): KeychainAdapter(api, service=selector)
        with self.assertRaisesRegex(ValueError, "^KEY_SIZE_INVALID$"):
            KeychainAdapter(api, service="diagnostic.service").create("diagnostic-account", bytes(31))

    def test_missing_is_not_invalid_query(self):
        api = Mock(); api.find.return_value = (ERR_ITEM_NOT_FOUND, ())
        with self.assertRaisesRegex(RuntimeError, "^KEY_RECORD_MISSING$"):
            KeychainAdapter(api, service="diagnostic.service").retrieve("diagnostic-account")


@unittest.skipUnless(os.environ.get("IIOS_RUN_DISPOSABLE_KEYCHAIN_TEST") == "1",
    "explicit disposable macOS Keychain acceptance only")
class CrossProcessDisposableAcceptance(unittest.TestCase):
    """Opt-in test; emits categories and lengths only, and always attempts cleanup."""

    SERVICE = "com.iios.expansion-wing.disposable.11c"
    ACCOUNT = "diagnostic-vector"
    CODE = r'''
import hashlib, sys
from expansion_wing.keychain_adapter import SecurityFrameworkAPI
api = SecurityFrameworkAPI(); service = b"com.iios.expansion-wing.disposable.11c"; account = b"diagnostic-vector"
operation = sys.argv[1]
if operation == "create_after_absence":
    status, values = api.find(service, account); assert status == -25300 and not values
    vector = bytes(range(32)); status = api.add(service, account, vector); assert status == 0
    print("process=A operation=create category=SUCCESS data_length=32 prior_absence=true")
elif operation == "retrieve":
    status, values = api.find(service, account); assert status == 0 and len(values) == 1
    value = values[0]; assert len(value) == 32
    assert hashlib.sha256(value).digest() == hashlib.sha256(bytes(range(32))).digest()
    print("process=B operation=retrieve category=SUCCESS data_length=32 hash_match=true")
elif operation == "duplicate":
    status = api.add(service, account, bytes(range(32))); assert status == -25299
    print("process=C operation=duplicate category=DUPLICATE_ITEM outcome=true")
elif operation == "delete":
    status = api.delete(service, account); assert status == 0
    print("process=D operation=delete category=SUCCESS outcome=true")
elif operation == "absence":
    status, values = api.find(service, account); assert status == -25300 and not values
    print("process=E operation=absence category=ITEM_NOT_FOUND outcome=true")
'''

    def process(self, operation: str) -> subprocess.CompletedProcess[str]:
        environment = {"LC_ALL": "C", "LANG": "C", "PYTHONPATH": os.environ["PYTHONPATH"]}
        return subprocess.run((sys.executable, "-c", self.CODE, operation), input="", text=True,
            capture_output=True, env=environment, timeout=10, check=True)

    def test_process_a_through_e(self):
        encoded_vector = base64.b64encode(bytes(range(32))).decode("ascii")
        try:
            for operation in ("create_after_absence", "retrieve", "duplicate", "delete", "absence"):
                result = self.process(operation)
                self.assertEqual(result.stderr, "")
                self.assertNotIn(encoded_vector, result.stdout + result.stderr)
                if operation == "create_after_absence":
                    self.assertTrue(SecurityCommandRunner().exists(service=self.SERVICE, account=self.ACCOUNT))
                if operation == "delete":
                    self.assertFalse(SecurityCommandRunner().exists(service=self.SERVICE, account=self.ACCOUNT))
        finally:
            api = SecurityFrameworkAPI()
            status = api.delete(self.SERVICE.encode(), self.ACCOUNT.encode())
            self.assertIn(status, (0, ERR_ITEM_NOT_FOUND))


if __name__ == "__main__": unittest.main()
