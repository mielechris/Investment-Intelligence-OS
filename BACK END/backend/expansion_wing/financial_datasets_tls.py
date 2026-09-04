from __future__ import annotations

import hashlib
import http.client
import os
import re
import socket
import ssl
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .financial_datasets import API_HOST, API_ORIGIN, AUTH_HEADER, FDResponse, FDCapability, canonical_request_target

TRUST_STATES = {"NOT_CONFIGURED", "BUNDLE_MISSING", "BUNDLE_UNSAFE", "BUNDLE_HASH_MISMATCH",
    "BUNDLE_INVALID", "READY", "TLS_VERIFICATION_FAILED", "CONTEXT_RESTRICTED"}
TLS_FAILURES = {"DNS_FAILED", "TCP_FAILED", "TLS_TRUST_NOT_CONFIGURED", "TLS_TRUST_UNSAFE",
    "TLS_TRUST_HASH_MISMATCH", "TLS_CERTIFICATE_VERIFICATION_FAILED", "TLS_PROTOCOL_FAILED",
    "TLS_HOSTNAME_FAILED", "TLS_TIMEOUT", "PROXY_CONTEXT_REJECTED", "ACCOUNTING_UNCERTAIN"}
_PEM_CERTIFICATE = re.compile(rb"-----BEGIN CERTIFICATE-----\r?\n.+?\r?\n-----END CERTIFICATE-----", re.S)
_PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


class FinancialDatasetsTransportError(RuntimeError):
    def __init__(self, category: str, *, request_started: bool) -> None:
        if category not in TLS_FAILURES: category = "ACCOUNTING_UNCERTAIN"
        super().__init__(category); self.category = category; self.request_started = request_started


@dataclass(frozen=True)
class TrustAssessment:
    state: str
    failure_category: str | None
    bundle_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.state not in TRUST_STATES: raise ValueError("TRUST_STATE_INVALID")


@dataclass(frozen=True)
class TrustBundlePolicy:
    bundle_path: Path | None = None
    expected_sha256: str | None = None
    maximum_bytes: int = 1_000_000

    def assess(self) -> TrustAssessment:
        if self.bundle_path is None or self.expected_sha256 is None:
            return TrustAssessment("NOT_CONFIGURED", "TLS_TRUST_NOT_CONFIGURED")
        if not re.fullmatch(r"[0-9a-f]{64}", self.expected_sha256):
            return TrustAssessment("BUNDLE_HASH_MISMATCH", "TLS_TRUST_HASH_MISMATCH")
        try: metadata = self.bundle_path.lstat()
        except (FileNotFoundError, NotADirectoryError):
            return TrustAssessment("BUNDLE_MISSING", "TLS_TRUST_NOT_CONFIGURED")
        except OSError:
            return TrustAssessment("CONTEXT_RESTRICTED", "TLS_TRUST_UNSAFE")
        if stat.S_ISLNK(metadata.st_mode):
            return TrustAssessment("BUNDLE_UNSAFE", "TLS_TRUST_UNSAFE")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try: descriptor = os.open(self.bundle_path, flags)
        except OSError:
            return TrustAssessment("CONTEXT_RESTRICTED", "TLS_TRUST_UNSAFE")
        try:
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or
                    metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
                return TrustAssessment("BUNDLE_UNSAFE", "TLS_TRUST_UNSAFE")
            if metadata.st_size <= 0 or metadata.st_size > self.maximum_bytes:
                return TrustAssessment("BUNDLE_INVALID", "TLS_TRUST_UNSAFE", metadata.st_size)
            chunks=[]; remaining=self.maximum_bytes+1
            while remaining:
                chunk=os.read(descriptor,min(65_536,remaining))
                if not chunk: break
                chunks.append(chunk); remaining-=len(chunk)
            content=b"".join(chunks)
            if len(content) != metadata.st_size:
                return TrustAssessment("BUNDLE_INVALID", "TLS_TRUST_UNSAFE", len(content))
        except OSError:
            return TrustAssessment("CONTEXT_RESTRICTED", "TLS_TRUST_UNSAFE")
        finally: os.close(descriptor)
        if hashlib.sha256(content).hexdigest() != self.expected_sha256:
            return TrustAssessment("BUNDLE_HASH_MISMATCH", "TLS_TRUST_HASH_MISMATCH", len(content))
        blocks = _PEM_CERTIFICATE.findall(content)
        if not blocks or content.count(b"-----BEGIN CERTIFICATE-----") != content.count(b"-----END CERTIFICATE-----"):
            return TrustAssessment("BUNDLE_INVALID", "TLS_TRUST_UNSAFE", len(content))
        return TrustAssessment("READY", None, len(content))

    def build_context(self) -> ssl.SSLContext:
        assessment = self.assess()
        if assessment.state != "READY":
            raise FinancialDatasetsTransportError(assessment.failure_category or "TLS_TRUST_UNSAFE",
                request_started=False)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try: context.load_verify_locations(cafile=str(self.bundle_path))
        except (OSError, ssl.SSLError):
            raise FinancialDatasetsTransportError("TLS_TRUST_UNSAFE", request_started=False) from None
        return context


ConnectionFactory = Callable[[str, int, ssl.SSLContext, float], Any]


def _connection(host: str, port: int, context: ssl.SSLContext, timeout: float):
    return http.client.HTTPSConnection(host=host, port=port, context=context, timeout=timeout)


class FinancialDatasetsHTTPSTransport:
    def __init__(self, trust: TrustBundlePolicy, *, connection_factory: ConnectionFactory = _connection,
                 environment: dict[str, str] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.trust = trust; self.connection_factory = connection_factory
        self.environment = os.environ if environment is None else environment; self.clock = clock
        self.last_trust_state = "NOT_CONFIGURED"

    def trust_readiness(self) -> str:
        if any(name in self.environment for name in _PROXY_NAMES): self.last_trust_state = "CONTEXT_RESTRICTED"
        else: self.last_trust_state = self.trust.assess().state
        return self.last_trust_state

    def __call__(self, base_url: str, headers: dict[str, bytes], tickers: tuple[str, ...],
                 connect_timeout: float, response_timeout: float) -> FDResponse:
        if any(name in self.environment for name in _PROXY_NAMES):
            raise FinancialDatasetsTransportError("PROXY_CONTEXT_REJECTED", request_started=False)
        if base_url != f"{API_ORIGIN}/company/facts" or len(tickers) != 1 or tuple(headers) != (AUTH_HEADER,):
            raise FinancialDatasetsTransportError("ACCOUNTING_UNCERTAIN", request_started=False)
        context = self.trust.build_context()
        target = canonical_request_target(FDCapability.COMPANY_FACTS, tickers[0])
        request_target = target.removeprefix(API_ORIGIN)
        connection = None; started = self.clock(); request_started = False
        try:
            request_started = True
            connection = self.connection_factory(API_HOST, 443, context, min(connect_timeout, response_timeout))
            connection.request("GET", request_target, headers={AUTH_HEADER: headers[AUTH_HEADER].decode("ascii")})
            response = connection.getresponse()
            body = response.read(2_000_001)
            redirect = response.getheader("Location") if 300 <= response.status < 400 else None
            return FDResponse(int(response.status), base_url, ("REDIRECT_PRESENT",) if redirect else (), body,
                max(0.0, (self.clock() - started) * 1000))
        except ssl.SSLCertVerificationError as exc:
            self.last_trust_state = "TLS_VERIFICATION_FAILED"
            category = "TLS_HOSTNAME_FAILED" if getattr(exc, "verify_code", None) == 62 else "TLS_CERTIFICATE_VERIFICATION_FAILED"
            raise FinancialDatasetsTransportError(category, request_started=request_started) from None
        except ssl.SSLError:
            self.last_trust_state = "TLS_VERIFICATION_FAILED"
            raise FinancialDatasetsTransportError("TLS_PROTOCOL_FAILED", request_started=request_started) from None
        except socket.gaierror:
            raise FinancialDatasetsTransportError("DNS_FAILED", request_started=request_started) from None
        except (ConnectionRefusedError, ConnectionResetError, BrokenPipeError):
            raise FinancialDatasetsTransportError("TCP_FAILED", request_started=request_started) from None
        except (TimeoutError, socket.timeout):
            raise FinancialDatasetsTransportError("TLS_TIMEOUT", request_started=request_started) from None
        except FinancialDatasetsTransportError:
            raise
        except Exception:
            raise FinancialDatasetsTransportError("ACCOUNTING_UNCERTAIN", request_started=request_started) from None
        finally:
            if connection is not None:
                try: connection.close()
                except Exception: pass


def browser_tls_readiness(*, credential_available: bool = False) -> dict[str, Any]:
    return {"schema_version": "iios-financial-datasets-tls-readiness-v1", "tls_transport": "AVAILABLE",
        "trust_bundle": "NOT_CONFIGURED", "certificate_verification_required": True,
        "hostname_verification_required": True, "minimum_tls": "TLS_1_2", "provider_network": "DISABLED",
        "credential": "AVAILABLE" if credential_available else "NOT_CONFIGURED", "provider_authority": False}
