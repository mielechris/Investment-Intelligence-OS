from main_v1_1 import app
from factory.router import router as factory_router
from factory.system_agents import ensure_system_agents
from intelligence.ingestion import ingestion_service


ensure_system_agents()
app.include_router(factory_router)
app.add_event_handler("startup", ingestion_service.start)
app.add_event_handler("shutdown", ingestion_service.stop)
