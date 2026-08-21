import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from intelligence.dispatcher import dispatcher
from intelligence.evidence_store import evidence_store
from intelligence.models import EvidenceItem
from intelligence.providers.alpha_vantage import AlphaVantageProvider
from intelligence.providers.coingecko import CoinGeckoProvider
from intelligence.providers.fred import FredProvider
from intelligence.providers.sec_company import fetch_recent_company_filings
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
    last_dispatched: int = 0

    def due(self, now: datetime) -> bool:
        return self.next_run_at is None or now >= self.next_run_at

    def schedule_next(self, now: datetime) -> None:
        self.next_run_at = now + timedelta(seconds=self.interval_seconds)


async def _fetch_sec_ipo() -> list[EvidenceItem]:
    packet = await fetch_recent_ipo_filings(count_per_form=25)
    return packet.items


async def _fetch_sec_company() -> list[EvidenceItem]:
    packet = await fetch_recent_company_filings(count_per_form=40)
    return packet.items


async def _fetch_crypto() -> list[EvidenceItem]:
    provider = CoinGeckoProvider()
    assets = [item.strip() for item in os.getenv("IIOS_CRYPTO_ASSETS", "bitcoin,ethereum").split(",") if item.strip()]
    items: list[EvidenceItem] = []
    for asset_id in assets:
        items.append(await asyncio.to_thread(provider.fetch, asset_id=asset_id, vs_currency="usd"))
    return items


async def _fetch_equities() -> list[EvidenceItem]:
    provider = AlphaVantageProvider()
    if not provider.status().configured:
        return []
    symbols = [
        item.strip().upper()
        for item in os.getenv("IIOS_EQUITY_SYMBOLS", "SPY,QQQ,IWM,DIA,AAPL,MSFT,NVDA,AMZN,META").split(",")
        if item.strip()
    ]
    items: list[EvidenceItem] = []
    for symbol in symbols:
        items.append(await asyncio.to_thread(provider.fetch_latest_daily, symbol=symbol))
        await asyncio.sleep(0.25)
    return items


async def _fetch_fred() -> list[EvidenceItem]:
    provider = FredProvider()
    if not provider.status().configured:
        return []
    series = [
        item.strip().upper()
        for item in os.getenv(
            "IIOS_FRED_SERIES",
            "FEDFUNDS,CPIAUCSL,CPILFESL,PCEPI,PCEPILFE,UNRATE,PAYEMS,DGS2,DGS10,DGS30,T10Y2Y,T10Y3M,VIXCLS,DTWEXBGS,DCOILWTICO,DCOILBRENTEU",
        ).split(",")
        if item.strip()
    ]
    items: list[EvidenceItem] = []
    for series_id in series:
        items.append(await asyncio.to_thread(provider.fetch, series_id=series_id))
    return items


class IngestionService:
    def __init__(self) -> None:
        self.jobs: list[IngestionJob] = [
            IngestionJob("sec_ipo", _env_int("IIOS_SEC_IPO_INTERVAL_SECONDS", 300), _fetch_sec_ipo),
            IngestionJob("sec_company", _env_int("IIOS_SEC_COMPANY_INTERVAL_SECONDS", 300), _fetch_sec_company),
            IngestionJob("crypto_market", _env_int("IIOS_CRYPTO_INTERVAL_SECONDS", 60), _fetch_crypto),
            IngestionJob("equity_market", _env_int("IIOS_EQUITY_INTERVAL_SECONDS", 900), _fetch_equities),
            IngestionJob("fred_macro", _env_int("IIOS_FRED_INTERVAL_SECONDS", 1800), _fetch_fred),
        ]
        self._task: asyncio.Task | None = None
        self._stopping = False
        self.last_auto_processing: dict = {"enabled": False, "processed": 0}

    async def run_job(self, job: IngestionJob) -> None:
        now = datetime.now(timezone.utc)
        job.last_started_at = now
        job.last_status = "running"
        job.last_error = None
        job.schedule_next(now)
        try:
            items = await job.fetcher()
            new_items: list[EvidenceItem] = []
            for item in items:
                inserted = await asyncio.to_thread(evidence_store.save, item)
                if inserted:
                    new_items.append(item)
            job.last_inserted = len(new_items)
            job.last_dispatched = await asyncio.to_thread(dispatcher.enqueue, new_items) if new_items else 0
            job.last_completed_at = datetime.now(timezone.utc)
            job.last_status = "ok"
        except Exception as exc:
            job.last_completed_at = datetime.now(timezone.utc)
            job.last_status = "error"
            job.last_error = str(exc)
            job.last_inserted = 0
            job.last_dispatched = 0

    async def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        due_jobs = [job for job in self.jobs if job.due(now)]
        if due_jobs:
            await asyncio.gather(*(self.run_job(job) for job in due_jobs))
        self.last_auto_processing = await asyncio.to_thread(dispatcher.process_pending)

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
            "dispatch_queue": dispatcher.counts(),
            "auto_agent_processing": self.last_auto_processing,
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
                    "last_dispatched": job.last_dispatched,
                }
                for job in self.jobs
            ],
            "paper_mode": True,
            "live_execution": False,
        }


ingestion_service = IngestionService()
