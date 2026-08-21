from main_v1_1 import app
from factory.router import router as factory_router
from factory.system_agents import ensure_system_agents


ensure_system_agents()
app.include_router(factory_router)
