from __future__ import annotations
from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select, and_
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Contract, ContractStatus, Customer, Plan
from app.schemas_recontract import RenewalCaseOut

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("/renewal-cases", response_model=list[RenewalCaseOut])
async def list_renewal_cases(session: AsyncSession = Depends(get_session)):
    today = date.today()
    first_of_month = today.replace(day=1)
    target_month = (first_of_month.replace(day=1) + timedelta(days=155)).replace(day=1)  # ≈5 months
    # Pick contracts whose END month == target_month AND status UNDER_CONTRACT
    q = (
        select(Contract)
        .options(joinedload(Contract.customer), joinedload(Contract.plan))
        .where(Contract.status == ContractStatus.UNDER_CONTRACT)
        .where(
            (Contract.end_date >= target_month) &
            (Contract.end_date < (target_month.replace(day=28) + timedelta(days=10)).replace(day=1))
        )
    )
    res = await session.execute(q)
    rows: list[Contract] = res.scalars().all()

    return [
        RenewalCaseOut(
            contract_id=c.id,
            customer_name=c.customer.name if c.customer else "",
            supply_point_number=c.supply_point_number,
            plan_name=c.plan.name if c.plan else "",
            end_date=c.end_date,
        )
        for c in rows
    ]
