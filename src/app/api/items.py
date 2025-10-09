from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import ItemIn, ItemOut
from app.models import Item
from app.db import get_session

router = APIRouter(prefix="/items", tags=["items"])

@router.post("", response_model=ItemOut, status_code=201)
async def create_item(item: ItemIn, session: AsyncSession = Depends(get_session)):
    row = Item(name=item.name, price=item.price)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ItemOut(id=row.id, name=row.name, price=row.price)

@router.get("", response_model=List[ItemOut])
async def list_items(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Item))
    rows = result.scalars().all()
    return [ItemOut(id=r.id, name=r.name, price=r.price) for r in rows]

@router.get("/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, session: AsyncSession = Depends(get_session)):
    row = await session.get(Item, item_id)
    if not row:
        raise HTTPException(404, "Not found")
    return ItemOut(id=row.id, name=row.name, price=row.price)
