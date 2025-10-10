from __future__ import annotations
from fastapi import FastAPI

from app.api.ppa_quotations import router as ppa_quotations_router
from app.api.recontract import router as recontract_router


app = FastAPI(title="Kumar's APIs")

app.include_router(ppa_quotations_router)
app.include_router(recontract_router)

@app.get("/healthz")
async def healthz():
    return {"ok": True}
