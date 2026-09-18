"""Recipe parity only. No key generation, native command or certificate use."""
from pathlib import Path
import unittest
from unittest.mock import Mock
from alpha_dummy_tls import create_dummy_tls

class DummyTlsTests(unittest.TestCase):
    def test_exact_existing_recipe_and_caller_transport(self):
        command=Mock();put=Mock();root=Path('/fixture')
        self.assertEqual(create_dummy_tls(root/'certificate.cnf',root,command=command,put=put),(root/'certificate.pem',root/'private-key.pem'))
        self.assertEqual(command.call_args.args[0],['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','1','-config','/fixture/certificate.cnf','-keyout','/fixture/private-key.pem','-out','/fixture/certificate.pem'])
        self.assertIn(b'subjectAltName=IP:127.0.0.1',put.call_args.args[1]);self.assertIn(b'SYNTHETIC TEST ONLY',put.call_args.args[1])
    def test_denied_transport_propagates_without_retry(self):
        command=Mock(side_effect=PermissionError(13,'not retained'))
        with self.assertRaises(PermissionError):create_dummy_tls('/fixture/config','/fixture',command=command,put=Mock())
        command.assert_called_once()
