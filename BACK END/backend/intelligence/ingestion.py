import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from intelligence.evidence_store import evidence_store
from intelligence.models import EvidenceItem
from intelligence.providers.coingecko import CoinGeckoProvider
from intelligence.providers.fred import FredProvider
from intelligence.providers.sec_ipo import fetch_recent_ipo_filings


Fetcher = Callable[[], Awaitable[list[EvidenceItem]]]


def _env_int(name: str, default: int) -> int:
    try:
        return max(5, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass
class IngestionJob:
    name: str
    interval_seconds: int
    fetcher: Fetcher
    next_run_at: datetime | None = None
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_status: str = "never_run"
    last_error: str | None = None
    last_inserted: int = 0

    def due(self, now: datetime) -> bool:
        return self.next_run_at is None or now >= self.next_run_at

    def schedule_next(self, now: datetime) -> None:
        self.next_run_at = now + timedelta(seconds=self.interval_seconds)


async def _fetch_sec_ipo() -> list[EvidenceItem]:
    packet = await fetch_recent_ipo_filings(count_per_form=25)
    return packet.items


async def _fetch_crypto() -> list[EvidenceItem]:
    provider = CoinGeckoProvider()
    assets = [
        item.strip()
        for item in os.getenv("IIOS_CRYPTO_ASSETS", "bitcoin,ethereum").split(",")
        if item.strip()
    ]
    items: list[EvidenceItem] = []
    for asset_id in assets:
        item = await asyncio.to_thread(provider.fetch, asset_id=asset_id, vs_currency="usd")
        items.append(item)
    return items


async def _fetch_fred() -> list[EvidenceItem]:
    provider = FredProvider()
    if not provider.status().configured:
        return []
    series = [
        item.strip().upper()
        for item in os.getenv(
            "IIOS_FRED_SERIES",
            "FEDFUNDS,CPIAUCSL,UNRATE,DGS2,DGS10,VIXCLS",
        ).split(",")
        if item.strip()
    ]
    items: list[EvidenceItem] = []
    for series_id in series:
        item = await asyncio.to_thread(provider.fetch, series_id=series_id)
        items.append(item)
    return items


class IngestionService:
    def __init__(self) -> None:
        self.jobs: list[IngestionJob] = [
            IngestionJob(
                name="sec_ipo",
                interval_seconds=_env_int("IIOS_SEC_IPO_INTERVAL_SECONDS", 300),
                fetcher=_fetch_sec_ipo,
            ),
            IngestionJob(
                name="crypto_market",
                interval_seconds=_env_int("IIOS_CRYPTO_INTERVAL_SECONDS", 60),
                fetcher=_fetch_crypto,
            ),
            IngestionJob(
                name="fred_macro",
                interval_seconds=_env_int("IIOS_FRED_INTERVAL_SECONDS", 1800),
                fetcher=_fetch_fred,
            ),
        ]
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def run_job(self, job: IngestionJob) -> None:
        now = datetime.now(timezone.utc)
        job.last_started_at = now
        job.last_status = "running"
        job.last_error = None
        job.schedule_next(now)
        try:
            items = await job.fetcher()
            inserted = await asyncio.to_thread(evidence_store.save_many, items)
            job.last_inserted = inserted
            job.last_completed_at = datetime.now(timezone.utc)
            job.last_status = "ok"
        except Exception as exc:
            job.last_completed_at = datetime.now(timezone.utc)
            job.last_status = "error"
            job.last_error = str(exc)
            job.last_inserted = 0

    async def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        due_jobs = [job for job in self.jobs if job.due(now)]
        if due_jobs:
            await asyncio.gather(*(self.run_job(job) for job in due_jobs))

    async def loop(self) -> None:
        self._stopping = False
        while not self._stopping:
            await self.run_once()
            await asyncio.sleep(5)

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.loop(), name="iios-ingestion-service")

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def status(self) -> dict:
        return {
            "running": self._task is not None and not self._task.done(),
            "evidence_count": evidence_store.count(),
            "jobs": [
                {
                    "name": job.name,
                    "interval_seconds": job.interval_seconds,
                    "last_started_at": job.last_started_at,
                    "last_completed_at": job.last_completed_at,
                    "next_run_at": job.next_run_at,
                    "last_status": job.last_status,
                    "last_error": job.last_error,
                    "last_inserted": job.last_inserted,
                }
                for job in self.jobs
            ],
            "paper_mode": True,
            "live_execution": False,
        }


ingestion_service = IngestionService()
