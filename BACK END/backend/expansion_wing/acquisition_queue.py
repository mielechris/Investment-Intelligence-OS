from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueuedSource:
    source_id: str
    domain: str
    priority: int
    source_type: str
    rights_state: str
    earliest_retrieval_time: str
    attempt_ceiling: int = 1


class OfficialSourceQueue:
    def __init__(self, approved_domains: set[str], *, max_depth: int = 20) -> None:
        self.approved_domains = approved_domains; self.max_depth = max_depth; self.items: dict[str, dict] = {}

    def admit(self, item: QueuedSource) -> str:
        if item.domain not in self.approved_domains: return "REJECTED_DOMAIN"
        if item.rights_state != "APPROVED": return "REJECTED_RIGHTS"
        if not 1 <= item.attempt_ceiling <= 2: return "REJECTED_ATTEMPT_CEILING"
        if item.source_id in self.items: return "DUPLICATE"
        if len(self.items) >= self.max_depth: return "BACKPRESSURE"
        self.items[item.source_id] = {"item": item, "attempts": 0, "state": "QUEUED"}; return "QUEUED"

    def record_attempt(self, source_id: str, *, successful: bool) -> str:
        record = self.items[source_id]
        if record["state"] in {"COMPLETE", "TERMINAL_FAILURE"}: return record["state"]
        record["attempts"] += 1
        if successful: record["state"] = "COMPLETE"
        elif record["attempts"] >= record["item"].attempt_ceiling: record["state"] = "TERMINAL_FAILURE"
        return record["state"]

    def view(self) -> dict:
        return {"count": len(self.items), "scheduled": False, "network_execution": False,
                "states": {state: sum(record["state"] == state for record in self.items.values())
                    for state in ("QUEUED", "COMPLETE", "TERMINAL_FAILURE")}}
