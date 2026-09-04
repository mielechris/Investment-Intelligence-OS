from __future__ import annotations

import base64
import secrets
import subprocess
import unittest
from unittest.mock import patch

from expansion_wing.keychain_adapter import (ERR_DUPLICATE_ITEM, ERR_ITEM_NOT_FOUND, SECURITY,
    KeychainAdapter, SecurityCommandRunner, decode_key_output, encode_key)


class MemoryAPI:
    def __init__(self): self.values = {}; self.fail = 0; self.ambiguous = False
    def add(self, service, account, secret):
        if self.fail: return self.fail
        if (service, account) in self.values: return ERR_DUPLICATE_ITEM
        self.values[(service, account)] = secret; return 0
    def find(self, service, account):
        if self.fail: return self.fail, ()
        value = self.values.get((service, account))
        if value is None: return ERR_ITEM_NOT_FOUND, ()
        return (0, (value, value)) if self.ambiguous else (0, (value,))
    def delete(self, service, account):
        if self.fail: return self.fail
        return 0 if self.values.pop((service, account), None) is not None else ERR_ITEM_NOT_FOUND


class EncodingTests(unittest.TestCase):
    def test_all_trailing_bytes_and_terminators(self):
        for final in range(256):
            key = bytes(range(31)) + bytes((final,)); encoded = encode_key(key)
            self.assertEqual(len(encoded), 44); self.assertTrue(encoded.endswith(b"="))
            for ending in (b"", b"\n", b"\r\n"):
                self.assertEqual(decode_key_output(encoded + ending), key)

    def test_binary_keys_are_byte_safe(self):
        for key in (bytes(32), b"\0\r\n" + bytes(range(29)), bytes(range(128, 160))):
            self.assertEqual(decode_key_output(encode_key(key)), key)

    def test_extra_lines_whitespace_invalid_padding_and_lengths_rejected(self):
        valid = encode_key(secrets.token_bytes(32))
        invalid = (valid + b"\n\n", valid + b" \n", b" " + valid, valid + b"\r", valid + b"\nextra",
            valid[:-1] + b"A", valid[:-2] + b"==", b"!" * 44,
            base64.b64encode(secrets.token_bytes(31)), base64.b64encode(secrets.token_bytes(33)))
        for value in invalid:
            with self.subTest(length=len(value)), self.assertRaisesRegex(RuntimeError, "KEY_ENCODING_INVALID"):
                decode_key_output(value)
        for key in (b"", secrets.token_bytes(31), secrets.token_bytes(33)):
            with self.assertRaisesRegex(ValueError, "KEY_SIZE_INVALID"): encode_key(key)


class FrameworkAdapterTests(unittest.TestCase):
    def test_exact_lifecycle_rotation_duplicate_ambiguity_and_idempotent_delete(self):
        api = MemoryAPI(); adapter = KeychainAdapter(api, service="com.iios.disposable")
        first, second = secrets.token_bytes(32), secrets.token_bytes(32)
        self.assertEqual(adapter.create("one", first), "CREATED")
        self.assertEqual(adapter.retrieve("one"), first)
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE"): adapter.create("one", second)
        self.assertEqual(adapter.rotate("one", "two", second, recovery_verified=True), "ROTATION_STAGED")
        self.assertEqual(adapter.retrieve("two"), second)
        api.ambiguous = True
        with self.assertRaisesRegex(RuntimeError, "AMBIGUOUS"): adapter.retrieve("one")
        api.ambiguous = False
        self.assertEqual(adapter.delete("one", human_authorized=True), "DELETED")
        self.assertEqual(adapter.delete("one", human_authorized=True), "ALREADY_ABSENT")
        with self.assertRaisesRegex(RuntimeError, "MISSING"): adapter.retrieve("missing")

    def test_nonzero_and_authorization_fail_closed_with_fixed_categories(self):
        api = MemoryAPI(); api.fail = -1; adapter = KeychainAdapter(api, service="com.iios.disposable")
        for operation in (lambda: adapter.create("one", secrets.token_bytes(32)), lambda: adapter.retrieve("one")):
            with self.assertRaisesRegex(RuntimeError, "KEYCHAIN_UNAVAILABLE"): operation()
        with self.assertRaisesRegex(PermissionError, "AUTHORIZATION_REQUIRED"):
            adapter.delete("one", human_authorized=False)


class CLIRunnerTests(unittest.TestCase):
    def test_absolute_fixed_no_shell_minimal_environment_and_no_diagnostics(self):
        completed = subprocess.CompletedProcess((SECURITY, "find-generic-password"), 0,
            stdout=b"metadata", stderr=b"private")
        with patch("expansion_wing.keychain_adapter.subprocess.run", return_value=completed) as invoked:
            self.assertTrue(SecurityCommandRunner().exists(service="com.iios.disposable", account="test"))
        self.assertEqual(invoked.call_args.args[0], (SECURITY, "find-generic-password", "-s",
            "com.iios.disposable", "-a", "test"))
        kwargs = invoked.call_args.kwargs
        self.assertFalse(kwargs["shell"]); self.assertEqual(kwargs["env"], {"LC_ALL": "C", "LANG": "C"})
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)

    def test_invalid_selector_timeout_and_nonzero(self):
        runner = SecurityCommandRunner()
        for service, account in (("", "test"), ("bad service", "test"), ("service", "bad account")):
            with self.assertRaisesRegex(ValueError, "SELECTOR_INVALID"):
                runner.exists(service=service, account=account)
        with patch("expansion_wing.keychain_adapter.subprocess.run", side_effect=subprocess.TimeoutExpired(SECURITY, 1)):
            with self.assertRaisesRegex(RuntimeError, "COMMAND_TIMEOUT"):
                runner.exists(service="com.iios.disposable", account="test")
        completed = subprocess.CompletedProcess((SECURITY, "find-generic-password"), 71,
            stdout=b"", stderr=b"secret")
        with patch("expansion_wing.keychain_adapter.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "COMMAND_FAILED") as raised:
                runner.exists(service="com.iios.disposable", account="test")
        self.assertNotIn("secret", str(raised.exception))


if __name__ == "__main__": unittest.main()
