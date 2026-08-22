from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


SourceKind = Literal[
    "policy",
    "macro",
    "market",
    "commodity",
    "weather",
    "geopolitical",
    "company",
    "other",
]

Freshness = Literal["fresh", "stale", "unknown"]


class EvidenceItem(BaseModel):
    source_name: str
    source_kind: SourceKind
    title: str
    url: str | None = None
    published_at: datetime | None = None
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    summary: str
    freshness: Freshness = "unknown"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class EvidencePacket(BaseModel):
    topic: str
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    items: list[EvidenceItem] = Field(default_factory=list)

    @property
    def source_count(self) -> int:
        return len(self.items)

    @property
    def fresh_source_count(self) -> int:
        return sum(1 for item in self.items if item.freshness == "fresh")


class TradeThesis(BaseModel):
    topic: str
    asset: str | None = None
    direction: Literal["LONG", "SHORT", "WATCH", "NO_TRADE"] = "WATCH"
    horizon: str = "unspecified"
    thesis: str
    catalysts: list[str] = Field(default_factory=list)
    invalidation: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    paper_mode: bool = True
