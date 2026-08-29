#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import iios_historical_macro_regime_library as core

SYSTEM_CURL = Path("/usr/bin/curl")
MAX_SERIES_WORKERS = 6


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


def _run_cycle_parallel(*, historical_dir: Path, macro_dir: Path):
    historical = core._read_json(historical_dir / "latest_historical_market_intelligence.json")
    series_data = {}
    provider_meta = {}
    series_ids = list(core.SERIES)
    workers = min(MAX_SERIES_WORKERS, max(1, len(series_ids)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="iios-10k-fred") as pool:
        futures = {pool.submit(core._fetch_series, series_id, macro_dir): series_id for series_id in series_ids}
        for future in as_completed(futures):
            series_id = futures[future]
            try:
                rows, meta = future.result()
            except Exception as exc:  # fail closed into the existing provider/error contract
                rows = []
                meta = {"provider": "FRED", "cache_hit": False, "error": f"{type(exc).__name__}: {exc}"}
            series_data[series_id] = rows
            provider_meta[series_id] = meta
    payload = core.build_library(historical=historical, series_data=series_data, provider_meta=provider_meta)
    payload["runtime_transport"] = "MACOS_SYSTEM_CURL_HTTP_1_1_VERIFIED_TLS_BOUNDED_RETRIES_PARALLEL_SERIES_FETCH"
    payload["runtime_series_workers"] = workers
    core._atomic_write(macro_dir / "latest_historical_macro_regime_library.json", payload)
    return payload


def install_runtime_patch() -> None:
    core._curl_text = _curl_text_http11
    core.run_cycle = _run_cycle_parallel


def main() -> int:
    install_runtime_patch()
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
