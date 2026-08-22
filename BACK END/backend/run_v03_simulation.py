import json
import os
import sys
from urllib import error, request

from chain_verifier import verify_audit


BASE_URL = os.getenv("IIOS_BASE_URL", "http://localhost:8000").rstrip("/")

SIMULATION_CASE = {
    "topic": "AI infrastructure demand may support semiconductor memory pricing, but the thesis should not advance without current market, company, positioning, and macro evidence.",
    "evidence": [
        {
            "source": "simulation://company-filing",
            "source_type": "company_filing",
            "claim": "The company reports exposure to AI-related memory demand.",
            "published_at": "2026-08-20T12:00:00Z",
            "observed_at": "2026-08-22T17:00:00Z",
            "reliability": 0.85,
        },
        {
            "source": "simulation://industry-data",
            "source_type": "industry_data",
            "claim": "Industry supply-demand conditions remain constructive but uncertain.",
            "published_at": "2026-08-21T12:00:00Z",
            "observed_at": "2026-08-22T17:00:00Z",
            "reliability": 0.75,
        },
        {
            "source": "simulation://macro-note",
            "source_type": "macro_research",
            "claim": "Rates and growth remain material valuation risks for technology equities.",
            "published_at": "2026-08-21T16:00:00Z",
            "observed_at": "2026-08-22T17:00:00Z",
            "reliability": 0.70,
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
        with request.urlopen(req, timeout=180) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            decoded = {"detail": raw}
        return exc.code, decoded


def main() -> int:
    print("IIOS v0.3/v0.4 governed factory simulation")
    print(f"Backend: {BASE_URL}")

    health_status, health = call_json("GET", "/")
    if health_status != 200:
        print(f"FAIL: backend health check returned {health_status}: {health}")
        return 1
    if health.get("paper_mode") is not True:
        print("FAIL: backend is not locked to PAPER MODE")
        return 1

    print(f"Backend version: {health.get('version')}")
    print("Running one governed investment case through the factory...")

    status, factory = call_json("POST", "/factory/run", SIMULATION_CASE)
    if status != 200:
        print(f"FAIL: /factory/run returned {status}: {factory}")
        return 1

    case_id = factory.get("case", {}).get("case_id")
    risk_authorization_id = factory.get("risk", {}).get("risk_authorization_id")
    if not case_id or not risk_authorization_id:
        print("FAIL: factory response is missing case or risk authorization lineage")
        return 1

    audit_status, audit = call_json("GET", f"/audit/{case_id}")
    if audit_status != 200:
        print(f"FAIL: audit retrieval returned {audit_status}: {audit}")
        return 1

    verification = verify_audit(audit)

    print("\nLINEAGE")
    for key, value in verification["lineage"].items():
        print(f"  {key}: {value}")

    print("\nPERSISTED COUNTS")
    for key, value in verification["counts"].items():
        print(f"  {key}: {value}")

    print("\nREPLAY-PROTECTION TEST")
    replay_status, replay = call_json(
        "POST",
        "/paper-execution/submit",
        {"risk_authorization_id": risk_authorization_id},
    )
    if replay_status != 409:
        verification["errors"].append(
            f"Expected replay attempt to return 409, received {replay_status}: {replay}"
        )
        verification["passed"] = False
        print(f"  FAIL: replay returned {replay_status}")
    else:
        print("  PASS: consumed authorization was rejected with HTTP 409")

    if verification["warnings"]:
        print("\nWARNINGS")
        for warning in verification["warnings"]:
            print(f"  - {warning}")

    if verification["errors"]:
        print("\nFAILURES")
        for failure in verification["errors"]:
            print(f"  - {failure}")
        print("\nRESULT: FAIL")
        return 1

    print("\nRESULT: PASS")
    print("The persisted governed chain is internally consistent and replay protection held.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
