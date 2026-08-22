from main import app
from learning_loop import router as learning_router


app.include_router(learning_router)
app.version = "0.5.0"
