from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict

router = APIRouter(prefix="/items", tags=["items"])

# Separate "input" and "output" models is a best practice:
# - ItemIn: what clients send to you
# - ItemOut: what you return (may include server fields like id)
class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    price: float = Field(gt=0)

class ItemOut(ItemIn):
    id: int

# In-memory "DB" for learning. For production, use a real database.
DB: Dict[int, ItemOut] = {}
_seq = 0

@router.post("", response_model=ItemOut, status_code=201)
def create_item(item: ItemIn):
    """Create an item, assign an ID, and store it."""
    global _seq
    _seq += 1
    obj = ItemOut(id=_seq, **item.model_dump())
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
