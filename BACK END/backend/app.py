import os

os.environ.setdefault(
    "IIOS_USER_AGENT",
    "Investment-Intelligence-OS/0.7 research-client github.com/mielechris/Investment-Intelligence-OS",
)

try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

from main import app
from learning_loop import router as learning_router
from ledger import latest_object
from monitoring_engine import (
    build_dashboard,
    router as monitoring_router,
    start_scheduler,
    stop_scheduler,
)
from public_case_router import router as public_case_router
from semiconductor_intelligence import router as semiconductor_router


@app.get("/monitoring/dashboard")
def monitoring_dashboard_live(limit: int = 25):
    """Return dashboard rows using the newest monitoring evidence when available."""
    dashboard = build_dashboard(limit)
    for row in dashboard.get("cases", []):
        case_id = str(row.get("case_id", ""))
        snapshot = latest_object("monitor_snapshot", case_id=case_id) if case_id else None
        summary = ((snapshot or {}).get("evidence_packet") or {}).get("summary") or {}
        if "average_quality_score" in summary:
            row["evidence_quality"] = summary.get("average_quality_score")
            row["latest_evidence_count"] = summary.get("evidence_count")
        reunderwrite = latest_object("full_reunderwrite", case_id=case_id) if case_id else None
        if reunderwrite:
            row["latest_reunderwrite_id"] = reunderwrite.get("full_reunderwrite_id")
            row["latest_reunderwrite_disposition"] = (reunderwrite.get("committee") or {}).get("disposition")
            row["latest_reunderwrite_confidence"] = (reunderwrite.get("committee") or {}).get("confidence")
    return dashboard


app.include_router(learning_router)
app.include_router(monitoring_router)
app.include_router(public_case_router)
app.include_router(semiconductor_router)
app.version = "0.7.0"


@app.on_event("startup")
def start_iios_monitoring() -> None:
    start_scheduler()


@app.on_event("shutdown")
def stop_iios_monitoring() -> None:
    stop_scheduler()


@app.get("/system/status")
def system_status():
    """Return the active governed-factory feature level."""
    return {
        "name": "Investment Intelligence OS",
        "version": "0.7.0",
        "paper_mode": True,
        "governed_chain": True,
        "persistent_ledger": True,
        "evidence_engine": True,
        "post_decision_learning": True,
        "judgment_bank": True,
        "automatic_monitoring": True,
        "factory_dashboard": True,
        "semiconductor_memory_intelligence": True,
        "automatic_ssl_cert_bundle": bool(os.getenv("SSL_CERT_FILE")),
    }
