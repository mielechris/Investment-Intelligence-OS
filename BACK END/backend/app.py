from main import app
from learning_loop import router as learning_router


app.include_router(learning_router)
app.version = "0.5.0"


@app.get("/system/status")
def system_status():
    return {
        "name": "Investment Intelligence OS",
        "version": "0.5.0",
        "paper_mode": True,
        "governed_chain": True,
        "persistent_ledger": True,
        "evidence_engine": True,
        "post_decision_learning": True,
        "judgment_bank": True,
    }
