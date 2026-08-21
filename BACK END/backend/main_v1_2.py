from main_v1_1 import app
from factory.router import router as factory_router


app.include_router(factory_router)
