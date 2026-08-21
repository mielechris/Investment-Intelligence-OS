from main import app
from intelligence.router import router as intelligence_router


app.include_router(intelligence_router)
