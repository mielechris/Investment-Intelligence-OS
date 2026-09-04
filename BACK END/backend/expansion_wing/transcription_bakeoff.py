from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TranscriptionAdapter(Protocol):
    name: str
    provider_activated: bool
    def transcribe(self, audio: bytes) -> dict: ...


@dataclass(frozen=True)
class CandidatePolicy:
    privacy_reviewed: bool
    retention_known: bool
    training_use_known: bool
    projected_cost: float | None
    local_offline: bool = False


def word_error_rate(reference: str, hypothesis: str) -> float:
    expected, actual = reference.split(), hypothesis.split()
    if not expected: return 0.0 if not actual else 1.0
    row = list(range(len(actual) + 1))
    for index, word in enumerate(expected, 1):
        next_row = [index]
        for offset, candidate in enumerate(actual, 1):
            next_row.append(min(next_row[-1] + 1, row[offset] + 1, row[offset - 1] + (word != candidate)))
        row = next_row
    return row[-1] / len(expected)


def evaluate_fixture(adapter: TranscriptionAdapter, policy: CandidatePolicy, *, audio: bytes,
                     reference: str, expected_speakers: tuple[str, ...], cost_ceiling: float = 0.0) -> dict:
    if adapter.provider_activated: raise PermissionError("PROVIDER_ACTIVATION_PROHIBITED")
    if not policy.privacy_reviewed or not policy.retention_known or not policy.training_use_known:
        return {"status": "REJECTED", "reason": "PROVIDER_POLICY_UNKNOWN"}
    if policy.projected_cost is None: return {"status": "REJECTED", "reason": "COST_UNKNOWN"}
    if policy.projected_cost > cost_ceiling: return {"status": "REJECTED", "reason": "COST_CEILING"}
    result = adapter.transcribe(audio)
    return {"status": "EVALUATED_FIXTURE", "candidate": adapter.name,
        "word_error_rate": word_error_rate(reference, str(result.get("text", ""))),
        "speaker_attribution_match": tuple(result.get("speakers", ())) == expected_speakers,
        "timestamps_present": bool(result.get("timestamps")), "latency_ms": result.get("latency_ms"),
        "projected_cost": policy.projected_cost, "local_offline": policy.local_offline,
        "provider_called": False}
