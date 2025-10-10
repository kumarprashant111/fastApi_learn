# src/app/main.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ppa_quotations import router as ppa_router
from app.api.recontract import router as recontract_router

app = FastAPI(title="FastAPI with uv (Postgres)")

# --- CORS (allow your local Next.js dev origin) ---
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # add other local tools if you use them:
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,     # must be explicit if allow_credentials=True
    allow_credentials=True,            # set to False if you don't send cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*", "Authorization", "Content-Type", "Accept"],
)

# --- Routers ---
app.include_router(ppa_router)           # /ppa_quotations
app.include_router(recontract_router)    # keep your recontract API

# --- Health check ---
@app.get("/healthz")
async def healthz():
    return {"ok": True}
