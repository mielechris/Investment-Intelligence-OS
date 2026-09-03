from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

MAX_QUOTATION_CHARS = 280


@dataclass(frozen=True)
class InvestorSourceNote:
    title: str
    source_url: str
    publisher: str
    published_at: str
    accessed_at: str
    source_type: str
    paraphrased_note: str
    limited_quotation: str
    right_to_use: bool

    def governed_record(self) -> dict[str, Any]:
        if not self.source_url.startswith(("https://", "http://", "fixture://")):
            raise ValueError("attributable source URL required")
        if not self.right_to_use:
            raise PermissionError("right to use required")
        if len(self.limited_quotation) > MAX_QUOTATION_CHARS:
            raise ValueError("quotation exceeds copyright-safe storage limit")
        if not self.paraphrased_note.strip():
            raise ValueError("structured paraphrased note required")
        identity = f"{self.source_url}|{self.published_at}|{self.paraphrased_note}".encode()
        return {**self.__dict__, "content_hash": hashlib.sha256(identity).hexdigest(),
                "complete_work_stored": False, "attributable": True, "human_review_required": True}
