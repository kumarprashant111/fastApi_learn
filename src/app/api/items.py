from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict

router = APIRouter(prefix="/items", tags=["items"])

# ----- Schemas -----
class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    price: float = Field(gt=0)

class ItemOut(ItemIn):
    id: int


# ----- In-memory store (dev only) -----
DB: Dict[int, ItemOut] = {}
_seq = 0

def _next_id() -> int:
    """Simple incremental ID generator for the in-memory store."""
    global _seq
    _seq += 1
    return _seq

def _seed() -> None:
    """
    Internal seeding function.
    Does nothing if DB already has data (avoids duplicate seeding).
    """
    if DB:
        return
    samples = [
        {"name": "Solar kWh Pack (Residential)", "price": 0.18},
        {"name": "Battery Storage Add-on", "price": 4.99},
        {"name": "Green Tariff (Business)", "price": 0.21},
    ]
    for s in samples:
        obj = ItemOut(id=_next_id(), **s)
        DB[obj.id] = obj

def seed() -> None:
    """
    Public seeding function you can call from app startup if desired.
    """
    _seed()

# Seed immediately on import so you see data on first run / reload.
_seed()


# ----- Routes -----
@router.post("", response_model=ItemOut, status_code=201)
def create_item(item: ItemIn):
    """Create an item, assign an ID, and store it."""
    obj = ItemOut(id=_next_id(), **item.model_dump())
    DB[obj.id] = obj
    return obj

@router.get("", response_model=list[ItemOut])
def list_items():
    """List all items."""
    return list(DB.values())

@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int):
    """Fetch a single item or return 404."""
    item = DB.get(item_id)
    if not item:
        raise HTTPException(404, "Not found")
    return item

@router.post("/_reset", status_code=204)
def reset_items():
    """
    Dev-only helper: clear the in-memory DB and reseed sample data.
    Useful when playing with create/update/delete during development.
    """
    DB.clear()
    global _seq
    _seq = 0
    _seed()
