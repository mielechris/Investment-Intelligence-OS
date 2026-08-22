import json
import os
import sys
from urllib import error, request


BASE_URL = os.getenv("IIOS_BASE_URL", "http://localhost:8000").rstrip("/")

FACTORY_CASE = {
    "topic": "AI infrastructure demand may support semiconductor memory pricing, subject to evidence quality, valuation, macro conditions, and thesis falsifiers.",
    "evidence": [
        {
            "source": "simulation://company",
            "source_type": "company",
            "evidence_type": "fundamental",
            "claim": "AI-related demand is a material contributor to the paper thesis.",
            "observed_at": "2026-08-22T17:00:00Z",
            "reliability_score": 0.85,
            "stance": "supports",
        },
        {
            "source": "simulation://macro",
            "source_type": "research",
            "evidence_type": "macro",
            "claim": "Rates and growth remain material valuation risks.",
            "observed_at": "2026-08-22T17:00:00Z",
            "reliability_score": 0.80,
            "stance": "contradicts",
        },
    ],
}


def call_json(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with request.urlopen(req, timeout=240) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            decoded = {"detail": raw}
        return exc.code, decoded


def fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def main() -> int:
    print("IIOS v0.5 post-decision learning simulation")
    print(f"Backend: {BASE_URL}")

    status, factory = call_json("POST", "/factory/run", FACTORY_CASE)
    if status != 200:
        return fail(f"factory returned {status}: {factory}")

    case_id = factory.get("case", {}).get("case_id")
    if not case_id:
        return fail("factory response missing case_id")

    learning_payload = {
        "case_id": case_id,
        "position": {
            "direction": "LONG",
            "reference_price": 100.0,
            "current_price": 94.0,
            "observations": ["Synthetic paper follow-up: price moved against the thesis."],
        },
        "thesis": {
            "falsifiers_triggered": ["fundamentals"],
            "catalyst_status": "MISSED",
            "drawdown_trigger_pct": 5.0,
            "notes": "Synthetic failure scenario for learning-loop verification.",
        },
        "reunderwrite": {
            "notes": "Broken thesis should force an exit recommendation in shadow mode."
        },
        "postmortem": {
            "outcome": "INVALIDATED",
            "realized_return_pct": -8.5,
            "horizon_days": 30,
            "notes": "Synthetic outcome used only to validate Judgment Bank mechanics.",
        },
    }
    status, learning = call_json("POST", "/learning-loop/run", learning_payload)
    if status != 200:
        return fail(f"learning loop returned {status}: {learning}")

    position = learning.get("position", {})
    thesis = learning.get("thesis", {})
    reunderwrite = learning.get("reunderwrite", {})
    postmortem = learning.get("postmortem", {}).get("postmortem", {})
    entries = learning.get("postmortem", {}).get("judgment_entries", [])

    checks = [
        (position.get("mode") == "SHADOW_CASE", "position monitor did not remain in SHADOW_CASE mode"),
        (position.get("paper_mode") is True, "position monitor is not paper mode"),
        (position.get("live_execution") is False, "position monitor exposed live execution"),
        (thesis.get("thesis_status") == "THESIS_BROKEN", "falsifier did not break the thesis"),
        (reunderwrite.get("action") == "EXIT_SHADOW_CASE", "broken thesis did not produce EXIT_SHADOW_CASE"),
        (postmortem.get("outcome") == "INVALIDATED", "post-mortem outcome mismatch"),
        (len(entries) == 8, f"expected 8 Judgment Bank entries, found {len(entries)}"),
    ]
    for passed, message in checks:
        if not passed:
            return fail(message)

    status, bank = call_json("GET", f"/judgment-bank/{case_id}")
    if status != 200:
        return fail(f"Judgment Bank case retrieval returned {status}: {bank}")
    if len(bank.get("judgment_entries", [])) != 8:
        return fail("persisted Judgment Bank does not contain 8 agent entries")

    status, scorecards = call_json("GET", "/judgment-bank/scorecards/all")
    if status != 200:
        return fail(f"scorecards returned {status}: {scorecards}")
    if len(scorecards.get("scorecards", [])) < 8:
        return fail("global scorecards do not contain all 8 specialist agents")

    status, audit = call_json("GET", f"/learning-loop/audit/{case_id}")
    if status != 200:
        return fail(f"learning audit returned {status}: {audit}")
    event_types = [event.get("event_type") for event in audit.get("events", [])]
    required = {
        "POSITION_MONITORED",
        "THESIS_MONITORED",
        "THESIS_BREAK_TRIGGERED",
        "REUNDERWRITE_COMPLETE",
        "POST_MORTEM_COMPLETE",
        "JUDGMENT_BANK_UPDATED",
    }
    missing = sorted(required - set(event_types))
    if missing:
        return fail(f"learning audit is missing events: {missing}")

    print("\nPOST-DECISION LINEAGE")
    print(f"  case_id: {case_id}")
    print(f"  position_monitor_id: {position.get('position_monitor_id')}")
    print(f"  thesis_monitor_id: {thesis.get('thesis_monitor_id')}")
    print(f"  reunderwrite_id: {reunderwrite.get('reunderwrite_id')}")
    print(f"  postmortem_id: {postmortem.get('postmortem_id')}")
    print(f"  judgment_entries: {len(entries)}")
    print("\nRESULT: PASS")
    print("The paper/shadow case completed the post-decision learning loop and updated the Judgment Bank.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
