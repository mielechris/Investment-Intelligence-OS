from main import app
from intelligence.feeds import router as feeds_router
from intelligence.router import router as intelligence_router


app.include_router(intelligence_router)
app.include_router(feeds_router)
