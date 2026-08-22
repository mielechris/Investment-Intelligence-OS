from main import app
from learning_loop import router as learning_router
from monitoring_engine import router as monitoring_router, start_scheduler, stop_scheduler
from public_case_router import router as public_case_router


app.include_router(learning_router)
app.include_router(monitoring_router)
app.include_router(public_case_router)
app.version = "0.6.0"


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
        "version": "0.6.0",
        "paper_mode": True,
        "governed_chain": True,
        "persistent_ledger": True,
        "evidence_engine": True,
        "post_decision_learning": True,
        "judgment_bank": True,
        "automatic_monitoring": True,
        "factory_dashboard": True,
    }
