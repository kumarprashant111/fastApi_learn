from __future__ import annotations
from fastapi import FastAPI

from app.api.recontract import router as recontracts_router
# Keep items if you still have it; otherwise remove imports/routes
try:
    from app.api.items import router as items_router  # optional demo
except Exception:
    items_router = None

app = FastAPI(title="FastAPI with uv (Postgres)")

app.include_router(recontracts_router)
if items_router:
    app.include_router(items_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
