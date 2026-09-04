from __future__ import annotations

import hashlib
import json
import os
import socket
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from expansion_wing.financial_datasets import (
    API_ORIGIN, AUTH_HEADER, CreditLedger, FDCapability, FDPolicy, FinancialDatasetsAdapter,
)
from expansion_wing.financial_datasets_tls import (
    FinancialDatasetsHTTPSTransport, FinancialDatasetsTransportError, TrustBundlePolicy,
    browser_tls_readiness,
)

SYNTHETIC_PEM = b"-----BEGIN CERTIFICATE-----\nU1lOVEhFVElDX1RFU1RfQ0VSVElGSUNBVEU=\n-----END CERTIFICATE-----\n"
SYNTHETIC_CREDENTIAL = b"synthetic_A1-key!opaque"


class Credentials:
    def __init__(self): self.calls = 0
    def retrieve(self): self.calls += 1; return SYNTHETIC_CREDENTIAL


class TrustBundleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.root = Path(self.directory.name)
    def tearDown(self): self.directory.cleanup()

    def write(self, content=SYNTHETIC_PEM, mode=0o600):
        path=self.root/"bundle.pem"; path.write_bytes(content); path.chmod(mode)
        return path,hashlib.sha256(content).hexdigest()

    def test_not_configured_missing_empty_and_oversized(self):
        self.assertEqual(TrustBundlePolicy().assess().state,"NOT_CONFIGURED")
        missing=self.root/"missing.pem"
        self.assertEqual(TrustBundlePolicy(missing,"0"*64).assess().state,"BUNDLE_MISSING")
        empty,digest=self.write(b"")
        self.assertEqual(TrustBundlePolicy(empty,digest).assess().state,"BUNDLE_INVALID")
        large,digest=self.write(SYNTHETIC_PEM+b"x"*32)
        self.assertEqual(TrustBundlePolicy(large,digest,maximum_bytes=len(SYNTHETIC_PEM)).assess().state,"BUNDLE_INVALID")

    def test_symlink_and_writable_modes_are_unsafe(self):
        path,digest=self.write(); link=self.root/"link.pem"; link.symlink_to(path)
        self.assertEqual(TrustBundlePolicy(link,digest).assess().state,"BUNDLE_UNSAFE")
        for mode in (0o620,0o602):
            path.chmod(mode)
            with self.subTest(mode=oct(mode)):
                self.assertEqual(TrustBundlePolicy(path,digest).assess().state,"BUNDLE_UNSAFE")

    def test_hash_invalid_pem_and_exact_verified_pem(self):
        path,digest=self.write()
        self.assertEqual(TrustBundlePolicy(path,"1"*64).assess().state,"BUNDLE_HASH_MISMATCH")
        invalid,bad_digest=self.write(b"not a certificate")
        self.assertEqual(TrustBundlePolicy(invalid,bad_digest).assess().state,"BUNDLE_INVALID")
        path,digest=self.write()
        self.assertEqual(TrustBundlePolicy(path,digest).assess().state,"READY")
        with patch.object(ssl.SSLContext,"load_verify_locations",return_value=None) as load:
            context=TrustBundlePolicy(path,digest).build_context()
        load.assert_called_once(); self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname); self.assertEqual(context.minimum_version,ssl.TLSVersion.TLSv1_2)

    def test_no_default_context_fallback_when_bundle_load_fails(self):
        path,digest=self.write()
        with patch.object(ssl.SSLContext,"load_verify_locations",side_effect=ssl.SSLError()):
            with self.assertRaisesRegex(FinancialDatasetsTransportError,"^TLS_TRUST_UNSAFE$"):
                TrustBundlePolicy(path,digest).build_context()


class FakeResponse:
    status=200
    def read(self,_limit): return b'{"data":[]}'
    def getheader(self,_name): return None


class FakeConnection:
    def __init__(self): self.request_args=None; self.closed=False
    def request(self,*args,**kwargs): self.request_args=(args,kwargs)
    def getresponse(self): return FakeResponse()
    def close(self): self.closed=True


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.path=Path(self.directory.name)/"bundle.pem"
        self.path.write_bytes(SYNTHETIC_PEM); self.path.chmod(0o600)
        self.trust=TrustBundlePolicy(self.path,hashlib.sha256(SYNTHETIC_PEM).hexdigest())
    def tearDown(self): self.directory.cleanup()

    def transport(self,factory,environment=None):
        return FinancialDatasetsHTTPSTransport(self.trust,connection_factory=factory,
            environment={} if environment is None else environment)

    def invoke(self,transport):
        with patch.object(ssl.SSLContext,"load_verify_locations",return_value=None):
            return transport(API_ORIGIN+"/company/facts",{AUTH_HEADER:SYNTHETIC_CREDENTIAL},("MU",),5,10)

    def test_exact_host_sni_port_path_and_secure_context(self):
        captured={}; connection=FakeConnection()
        def factory(host,port,context,timeout): captured.update(host=host,port=port,context=context,timeout=timeout); return connection
        result=self.invoke(self.transport(factory))
        self.assertEqual((captured["host"],captured["port"]),("api.financialdatasets.ai",443))
        self.assertEqual(connection.request_args[0],("GET","/company/facts?ticker=MU"))
        self.assertEqual(tuple(connection.request_args[1]["headers"]),(AUTH_HEADER,))
        self.assertEqual(captured["context"].verify_mode,ssl.CERT_REQUIRED); self.assertTrue(captured["context"].check_hostname)
        self.assertEqual(captured["context"].minimum_version,ssl.TLSVersion.TLSv1_2); self.assertEqual(result.status,200)

    def test_alternate_target_and_proxy_context_rejected_before_connection(self):
        for base in ("http://api.financialdatasets.ai/company/facts","https://127.0.0.1/company/facts",
                "https://api.financialdatasets.ai:444/company/facts","https://other.example/company/facts"):
            with self.subTest(base=base),self.assertRaisesRegex(FinancialDatasetsTransportError,"^ACCOUNTING_UNCERTAIN$"):
                self.invoke(self.transport(lambda *_: self.fail("connection attempted"))) if base==API_ORIGIN+"/company/facts" else \
                    self.transport(lambda *_: self.fail("connection attempted"))(base,{AUTH_HEADER:SYNTHETIC_CREDENTIAL},("MU",),5,10)
        proxy=self.transport(lambda *_: self.fail("connection attempted"),{"HTTPS_PROXY":"private"})
        with self.assertRaisesRegex(FinancialDatasetsTransportError,"^PROXY_CONTEXT_REJECTED$"):
            proxy(API_ORIGIN+"/company/facts",{AUTH_HEADER:SYNTHETIC_CREDENTIAL},("MU",),5,10)

    def test_fixed_tls_dns_tcp_timeout_and_unknown_classification(self):
        class HostnameFailure(ssl.SSLCertVerificationError): verify_code=62
        cases=((socket.gaierror(),"DNS_FAILED"),(ConnectionRefusedError(),"TCP_FAILED"),
            (ConnectionResetError(),"TCP_FAILED"),(ssl.SSLCertVerificationError(),"TLS_CERTIFICATE_VERIFICATION_FAILED"),
            (HostnameFailure(),"TLS_HOSTNAME_FAILED"),(ssl.SSLError(),"TLS_PROTOCOL_FAILED"),
            (TimeoutError(),"TLS_TIMEOUT"),(RuntimeError("private"),"ACCOUNTING_UNCERTAIN"))
        for error,category in cases:
            with self.subTest(category=category):
                with self.assertRaises(FinancialDatasetsTransportError) as raised:
                    self.invoke(self.transport(lambda *_args,e=error: (_ for _ in ()).throw(e)))
                self.assertEqual((raised.exception.category,raised.exception.request_started),(category,True))
                self.assertNotIn("private",str(raised.exception))

    def test_missing_trust_stops_before_keychain_network_and_credit(self):
        credentials=Credentials(); calls=[]
        transport=FinancialDatasetsHTTPSTransport(TrustBundlePolicy(),connection_factory=lambda *_: calls.append(1),environment={})
        adapter=FinancialDatasetsAdapter(FDPolicy(enabled=True,provider_balance=1000),credentials=credentials,transport=transport)
        result=adapter.fetch(FDCapability.COMPANY_FACTS,("MU",))
        self.assertEqual((result.failure,credentials.calls,calls,adapter.credits.consumed),
            ("TLS_TRUST_NOT_CONFIGURED",0,[],0))

    def test_http_status_is_returned_not_misclassified_as_tls(self):
        class HTTPFailure(FakeResponse):
            def __init__(self,status): self.status=status
        for status in (401,403):
            connection=FakeConnection(); connection.getresponse=lambda s=status: HTTPFailure(s)
            response=self.invoke(self.transport(lambda *_: connection))
            self.assertEqual(response.status,status)

    def test_browser_projection_is_scalar_and_path_free(self):
        value=browser_tls_readiness(); encoded=json.dumps(value,sort_keys=True)
        self.assertEqual((value["tls_transport"],value["trust_bundle"],value["minimum_tls"]),
            ("AVAILABLE","NOT_CONFIGURED","TLS_1_2"))
        self.assertTrue(value["certificate_verification_required"] and value["hostname_verification_required"])
        self.assertFalse(value["provider_authority"]); self.assertNotIn("bundle_path",encoded)


if __name__ == "__main__": unittest.main()
