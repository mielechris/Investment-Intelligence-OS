#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

import iios_historical_macro_regime_library as core

SYSTEM_CURL = Path("/usr/bin/curl")


def _curl_text_http11(url: str) -> str:
    command = str(SYSTEM_CURL if SYSTEM_CURL.exists() else "curl")
    result = subprocess.run(
        [
            command,
            "--http1.1",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--connect-timeout",
            "10",
            "--max-time",
            "60",
            "--retry",
            "3",
            "--retry-delay",
            "1",
            "--retry-all-errors",
            "--user-agent",
            "Investment-Intelligence-OS/1.0 macro-regime",
            url,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "curl failed").strip()
        raise RuntimeError(f"system curl HTTP/1.1 failed ({result.returncode}): {detail[:800]}")
    return result.stdout


def install_runtime_patch() -> None:
    core._curl_text = _curl_text_http11


def main() -> int:
    install_runtime_patch()
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
