from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import (
    Contract, ContractStatus, RecontractEstimate, RecontractSupplyPoint, RecontractPlant,
    Plan, Customer, QuoteEffectiveDays
)
from app.schemas_recontract import RecontractEstimateIn, RecontractEstimateOut

router = APIRouter(prefix="/recontracts", tags=["recontracts"])


@router.post("", response_model=RecontractEstimateOut, status_code=status.HTTP_201_CREATED)
async def create_recontract_estimate(payload: RecontractEstimateIn, session: AsyncSession = Depends(get_session)):
    # -- Validate FKs so we fail with 400 instead of DB 500 --
    if not await session.get(Plan, payload.plan_id):
        raise HTTPException(status_code=400, detail=f"Invalid plan_id: {payload.plan_id}")
    if not await session.get(Customer, payload.customer_id):
        raise HTTPException(status_code=400, detail=f"Invalid customer_id: {payload.customer_id}")

    # -- Coerce enum explicitly (even if schema already did) --
    try:
        qeff = QuoteEffectiveDays(payload.quote_effective_days)
    except Exception:
        raise HTTPException(status_code=400, detail="quote_effective_days must be 30 or 60")

    est = RecontractEstimate(
        plan_id=payload.plan_id,
        customer_id=payload.customer_id,
        desired_quote_date=payload.desired_quote_date,
        quote_effective_days=qeff,  # ✅ exact enum class
        remarks=payload.remarks,
    )
    session.add(est)
    await session.flush()  # est.id is available

    # Supply points
    for sp in payload.supply_points:
        session.add(RecontractSupplyPoint(estimate_id=est.id, supply_point_number=sp.supply_point_number))

    # Default 0.0 MW + user scenarios
    session.add(RecontractPlant(estimate_id=est.id, capacity_mw=0.0, ppa_unit_price_yen_per_kwh=None))
    for p in payload.plants:
        session.add(RecontractPlant(
            estimate_id=est.id,
            capacity_mw=p.capacity_mw,
            ppa_unit_price_yen_per_kwh=p.ppa_unit_price_yen_per_kwh
        ))

    # Flip contract status on matching SPNs
    if payload.supply_points:
        spns = [sp.supply_point_number for sp in payload.supply_points]
        await session.execute(
            update(Contract)
            .where(Contract.supply_point_number.in_(spns))
            .where(Contract.status == ContractStatus.UNDER_CONTRACT)
            .values(status=ContractStatus.RECONTRACT_ESTIMATE)
        )

    try:
        await session.commit()
    except IntegrityError as e:
        # FK violations, enum issues, etc → surface clearly
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"Database constraint error: {str(e.orig)}")

    # -- Eager-load relationships before returning (avoids MissingGreenlet) --
    result = await session.execute(
        select(RecontractEstimate)
        .options(
            selectinload(RecontractEstimate.supply_points),
            selectinload(RecontractEstimate.plants),
        )
        .where(RecontractEstimate.id == est.id)
    )
    est_loaded = result.scalar_one()
    return est_loaded


@router.get("/{estimate_id}", response_model=RecontractEstimateOut)
async def get_estimate(estimate_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(RecontractEstimate)
        .options(
            selectinload(RecontractEstimate.supply_points),
            selectinload(RecontractEstimate.plants),
        )
        .where(RecontractEstimate.id == estimate_id)
    )
    est = result.scalar_one_or_none()
    if not est:
        raise HTTPException(404, "Estimate not found")
    return est
