from fastapi import FastAPI
from sqlalchemy import select
from app.api.items import router as items_router
from app.settings import settings
from app.db import get_session
from app.models import Item

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.include_router(items_router)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.on_event("startup")
async def seed_if_empty():
    # Seed a few items if the table is empty
    async for session in get_session():
        result = await session.execute(select(Item))
        if result.scalars().first() is None:
            session.add_all([
                Item(name="Solar kWh Pack (Residential)", price=0.18),
                Item(name="Battery Storage Add-on", price=4.99),
                Item(name="Green Tariff (Business)", price=0.21),
            ])
            await session.commit()
