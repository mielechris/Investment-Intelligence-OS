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


def configure_verified_tls() -> dict[str, Any]:
    """Ensure urllib/OpenSSL can find a verified CA bundle without disabling TLS checks.

    Resolution order:
      1. Respect an already configured, existing SSL_CERT_FILE.
      2. Prefer the active Python environment's certifi bundle.
      3. Fall back to the platform/OpenSSL default trust store only if it can
         successfully create a normal verified default context.

    This function never installs an unverified HTTPS context and never sets a
    flag that bypasses hostname or certificate verification.
    """
    existing = _existing_ca_file()
    if existing:
        return {
            "configured": True,
            "mode": "EXISTING_SSL_CERT_FILE",
            "certificate_verification": True,
            "hostname_verification": True,
        }

    certifi_file = _certifi_ca_file()
    if certifi_file:
        os.environ["SSL_CERT_FILE"] = certifi_file
        # Some providers/libraries inspect this conventional variable too. It
        # points to the same verified CA bundle; it does not change TLS policy.
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi_file)
        # Prove the selected bundle can construct a normal verified context.
        context = ssl.create_default_context(cafile=certifi_file)
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise RuntimeError("VERIFIED_TLS_CONTEXT_NOT_ENFORCED")
        return {
            "configured": True,
            "mode": "CERTIFI_CA_BUNDLE",
            "certificate_verification": True,
            "hostname_verification": True,
        }

    context = ssl.create_default_context()
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise RuntimeError("PLATFORM_TLS_CONTEXT_NOT_VERIFIED")
    return {
        "configured": True,
        "mode": "PLATFORM_DEFAULT_CA_STORE",
        "certificate_verification": True,
        "hostname_verification": True,
    }
