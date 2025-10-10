from __future__ import annotations
from fastapi import FastAPI

from app.api.projects import router as projects_router
# keep your existing recontract endpoints if you have them:
from app.api.recontract import router as recontract_router


app = FastAPI(title="FastAPI with uv (Postgres)")

app.include_router(projects_router)
app.include_router(recontract_router)

@app.get("/healthz")
async def healthz():
    return {"ok": True}
