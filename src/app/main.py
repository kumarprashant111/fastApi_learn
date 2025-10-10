# src/app/main.py
from __future__ import annotations
from fastapi import FastAPI

from app.api.ppa_quotations import router as ppa_router
from app.api.recontract import router as recontract_router  # keep your recontract API

app = FastAPI(title="FastAPI with uv (Postgres)")

app.include_router(ppa_router)           # ✅ only this for quotations
app.include_router(recontract_router)

@app.get("/healthz")
async def healthz():
    return {"ok": True}
