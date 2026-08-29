from __future__ import annotations

import os
import ssl
from pathlib import Path
from typing import Any


def _existing_ca_file() -> str | None:
    value = str(os.getenv("SSL_CERT_FILE") or "").strip()
    if value and Path(value).expanduser().is_file():
        return str(Path(value).expanduser())
    return None


def _certifi_ca_file() -> str | None:
    try:
        import certifi
    except Exception:  # noqa: BLE001
        return None
    try:
        value = str(certifi.where() or "").strip()
    except Exception:  # noqa: BLE001
        return None
    return value if value and Path(value).is_file() else None


def _install_resilient_index_sources() -> None:
    """Install the governed production source resolver after TLS is trustworthy.

    The resolver still tries the S&P publisher directly first. If that publisher
    blocks machine access or does not expose a complete machine-readable list, it
    may use BlackRock iShares IVV first-party holdings as an explicitly labeled
    S&P 500 tracker mirror. Nasdaq remains publisher-direct. No acceptance-only
    Yahoo screener data can satisfy the governed universe contract.
    """
    from production_index_universe_resilient import install_into_legacy_module

    install_into_legacy_module()


def _status(mode: str) -> dict[str, Any]:
    _install_resilient_index_sources()
    return {
        "configured": True,
        "mode": mode,
        "certificate_verification": True,
        "hostname_verification": True,
        "resilient_index_sources_installed": True,
    }


def configure_verified_tls() -> dict[str, Any]:
    """Ensure urllib/OpenSSL can find a verified CA bundle without disabling TLS checks.

    Resolution order:
      1. Respect an already configured, existing SSL_CERT_FILE.
      2. Prefer the active Python environment's certifi bundle.
      3. Fall back to the platform/OpenSSL default trust store only if it can
         successfully create a normal verified default context.

    This function never installs an unverified HTTPS context and never sets a
    flag that bypasses hostname or certificate verification. Once a verified
    context is established it also installs the governed resilient index-source
    resolver used by Batch 9E production discovery.
    """
    existing = _existing_ca_file()
    if existing:
        context = ssl.create_default_context(cafile=existing)
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise RuntimeError("VERIFIED_TLS_CONTEXT_NOT_ENFORCED")
        return _status("EXISTING_SSL_CERT_FILE")

    certifi_file = _certifi_ca_file()
    if certifi_file:
        os.environ["SSL_CERT_FILE"] = certifi_file
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi_file)
        context = ssl.create_default_context(cafile=certifi_file)
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise RuntimeError("VERIFIED_TLS_CONTEXT_NOT_ENFORCED")
        return _status("CERTIFI_CA_BUNDLE")

    context = ssl.create_default_context()
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise RuntimeError("PLATFORM_TLS_CONTEXT_NOT_VERIFIED")
    return _status("PLATFORM_DEFAULT_CA_STORE")
