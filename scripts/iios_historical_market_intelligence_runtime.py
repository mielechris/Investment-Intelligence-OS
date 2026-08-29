#!/usr/bin/env python3
from __future__ import annotations

import os

# Reuse the certificate bundle already used by IIOS provider_hardening when it
# is available in the active backend environment. This keeps the standalone
# 10H archive worker aligned with the provider path that already works on the
# Mac, while remaining portable in CI/test environments where certifi may not
# be installed.
try:
    import certifi  # type: ignore
except ImportError:
    certifi = None

if certifi is not None:
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from iios_historical_market_intelligence import main


if __name__ == "__main__":
    raise SystemExit(main())
