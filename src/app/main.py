from fastapi import FastAPI
from app.api.items import router as items_router
from app.settings import settings
app = FastAPI(title=settings.app_name, debug=settings.debug)


app = FastAPI(title="FastAPI with uv")
app.include_router(items_router)

@app.get("/health")
def health():
    return {"status": "ok"}
