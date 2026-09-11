import contextlib
import io
import unittest
from urllib.parse import quote

from provider_gateway_credentials import MacKeychain, SecretMaterial, credential_scope
from test_provider_gateway_live_contract import admitted, NOW

FAKE = b'FAKE_KEY_FOR_OFFLINE_TEST_ONLY_012345'


class FakeCredentials:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def read(self, service, account):
        self.calls.append((service, account))
        if len(self.calls) == self.fail_at:
            raise RuntimeError(FAKE.decode())
        return FAKE


class CredentialTests(unittest.TestCase):
    def test_exact_pair_and_cleanup(self):
        backend = FakeCredentials()
        with credential_scope(admitted(), backend=backend, now=NOW) as material:
            self.assertEqual(len(material.values()), 2)
            self.assertNotIn(FAKE.decode(), repr(material))
        self.assertEqual(backend.calls, [('IIOS_ALPACA_PAPER_API_KEY', 'iios-provider'), ('IIOS_ALPACA_PAPER_API_SECRET', 'iios-provider')])
        with self.assertRaises(ValueError):
            material.values()

    def test_cleanup_after_caller_exception(self):
        with self.assertRaises(RuntimeError):
            with credential_scope(admitted(), backend=FakeCredentials(), now=NOW) as material:
                raise RuntimeError('synthetic')
        with self.assertRaises(ValueError):
            material.values()

    def test_resolver_error_never_echoes(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            with self.assertRaises(ValueError) as caught:
                with credential_scope(admitted(), backend=FakeCredentials(2), now=NOW):
                    self.fail('unreachable')
        self.assertNotIn(FAKE.decode(), str(caught.exception) + stream.getvalue())
        self.assertIsNone(caught.exception.__context__)

    def test_missing_admission_before_backend(self):
        fake = FakeCredentials()
        with self.assertRaises(ValueError):
            with credential_scope(None, backend=fake, now=NOW):
                self.fail('unreachable')
        self.assertEqual(fake.calls, [])

    def test_real_keychain_cannot_enter_offline_scope(self):
        with self.assertRaises(ValueError):
            with credential_scope(admitted(), backend=MacKeychain(), now=NOW):
                self.fail('unreachable')

    def test_invalid_credential_encoding(self):
        fake = FakeCredentials()
        fake.read = lambda *_: b'newline\nnot_allowed'
        with self.assertRaises(ValueError):
            with credential_scope(admitted(), backend=fake, now=NOW):
                self.fail('unreachable')

    def test_encoded_echoes(self):
        import base64
        material = SecretMaterial([FAKE])
        for value in (FAKE, quote(FAKE.decode()).encode(), base64.b64encode(FAKE)):
            with self.assertRaises(ValueError):
                material.reject_echo(value)
        material.close()
