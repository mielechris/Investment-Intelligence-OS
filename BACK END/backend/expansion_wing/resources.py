from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResourceBudget:
    max_cpu_pct: float = 60.0
    max_memory_mb: int = 2048
    max_concurrent_ai_tasks: int = 2
    provider_requests_per_day: int = 100
    provider_cost_per_day: float = 10.0
    max_queue_depth: int = 200


@dataclass
class ResourceGovernor:
    budget: ResourceBudget = field(default_factory=ResourceBudget)
    content_hashes: set[str] = field(default_factory=set)

    def admit(self, *, priority: int, cpu_pct: float, memory_mb: int, active_ai_tasks: int,
              requests_today: int, known_cost_today: float | None, queue_depth: int,
              content: bytes = b"", optional: bool = True) -> dict[str, Any]:
        reasons: list[str] = []
        digest = hashlib.sha256(content).hexdigest() if content else None
        if digest and digest in self.content_hashes:
            reasons.append("CONTENT_DUPLICATE")
        if cpu_pct > self.budget.max_cpu_pct: reasons.append("CPU_BUDGET")
        if memory_mb > self.budget.max_memory_mb: reasons.append("MEMORY_BUDGET")
        if active_ai_tasks >= self.budget.max_concurrent_ai_tasks: reasons.append("AI_CONCURRENCY_BUDGET")
        if requests_today >= self.budget.provider_requests_per_day: reasons.append("PROVIDER_REQUEST_BUDGET")
        if known_cost_today is None: reasons.append("PROVIDER_COST_UNKNOWN")
        elif known_cost_today >= self.budget.provider_cost_per_day: reasons.append("PROVIDER_COST_BUDGET")
        if queue_depth >= self.budget.max_queue_depth: reasons.append("QUEUE_BACKPRESSURE")
        if optional and priority > 5 and reasons: reasons.append("OPTIONAL_JOB_SUSPENDED")
        admitted = not reasons
        if admitted and digest:
            self.content_hashes.add(digest)
        return {"admitted": admitted, "reasons": sorted(set(reasons)), "priority": priority,
                "fail_closed": True, "market_collection_protected": priority > 1}
