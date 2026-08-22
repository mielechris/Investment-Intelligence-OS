from contextlib import asynccontextmanager

from main_v1_1 import app
from factory.router import router as factory_router
from factory.system_agents import ensure_system_agents
from intelligence.council_router import router as council_router
from intelligence.ingestion import ingestion_service
from intelligence.memory_router import router as memory_router


ensure_system_agents()
app.include_router(factory_router)
app.include_router(memory_router)
app.include_router(council_router)

_original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(app_instance):
    async with _original_lifespan(app_instance):
        await ingestion_service.start()
        try:
            yield
        finally:
            await ingestion_service.stop()


app.router.lifespan_context = lifespan
