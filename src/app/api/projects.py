# src/app/api/projects.py
from __future__ import annotations
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, cast, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import ARRAY, array

from app.db import get_session
from app.models import (
    PpaBundle,
    PpaProject,
    PpaSupplyPoint,
    Plan,
    Customer,
    Agency,
    QuoteStatus,
    OfferStatus,
)
from app.schemas_projects import ProjectListRow

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=List[ProjectListRow])
async def list_projects(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    customer_id: Optional[int] = None,
    agency_id: Optional[int] = None,
    area: Optional[str] = None,
    quote_status: Optional[str] = None,
    offer_status: Optional[str] = None,
) -> List[ProjectListRow]:
    """
    Lists PPA bundles with a few rollups:
      - number of supply points
      - total contracted kW
      - array of project IDs
    """

    # --- base selectable -----------------------------------------------------
    stmt = (
        select(
            PpaBundle.id.label("bundle_id"),
            Plan.name.label("plan_name"),
            Customer.name.label("customer_name"),
            Agency.name.label("agency_name"),
            PpaBundle.area,
            func.count(PpaSupplyPoint.id).label("sp_count"),
            func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw"),
            PpaBundle.contract_start_date,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
            # Typed empty array fallback to avoid NullType() in COALESCE
            func.coalesce(
                func.array_agg(func.distinct(PpaProject.id)),
                cast(array([], type_=Integer), ARRAY(Integer)),
            ).label("proj_ids"),
        )
        .join(Plan, Plan.id == PpaBundle.plan_id)
        .join(Customer, Customer.id == PpaBundle.customer_id)
        .outerjoin(Agency, Agency.id == PpaBundle.agency_id)
        .outerjoin(PpaSupplyPoint, PpaSupplyPoint.bundle_id == PpaBundle.id)
        .outerjoin(PpaProject, PpaProject.bundle_id == PpaBundle.id)
        .group_by(
            PpaBundle.id,
            Plan.name,
            Customer.name,
            Agency.name,
            PpaBundle.area,
            PpaBundle.contract_start_date,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
        )
        .order_by(PpaBundle.id.desc())
        .limit(size)
        .offset((page - 1) * size)
    )

    # --- filters -------------------------------------------------------------
    if customer_id is not None:
        stmt = stmt.where(PpaBundle.customer_id == customer_id)

    if agency_id is not None:
        stmt = stmt.where(PpaBundle.agency_id == agency_id)

    if area:
        stmt = stmt.where(PpaBundle.area == area)

    if quote_status:
        try:
            qs = QuoteStatus(quote_status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid quote_status '{quote_status}'. "
                       f"Allowed: {[e.value for e in QuoteStatus]}",
            )
        stmt = stmt.where(PpaBundle.quote_status == qs)

    if offer_status:
        try:
            os_ = OfferStatus(offer_status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid offer_status '{offer_status}'. "
                       f"Allowed: {[e.value for e in OfferStatus]}",
            )
        stmt = stmt.where(PpaBundle.offer_status == os_)

    # --- execute -------------------------------------------------------------
    rows = (await session.execute(stmt)).all()

    # --- shape response ------------------------------------------------------
    out: List[ProjectListRow] = []
    for r in rows:
        out.append(
            ProjectListRow(
                id=r.bundle_id,
                project_numbers=[int(pid) for pid in (r.proj_ids or []) if pid is not None],
                plan=r.plan_name,
                customer=r.customer_name,
                agency=r.agency_name,
                area=r.area,
                supply_point_count=int(r.sp_count or 0),
                contracted_power_kw=float(r.sum_kw or 0.0),
                annual_usage_kwh=0.0,  # TODO: wire up when usage table exists
                contract_start_date=r.contract_start_date,
                expiration_date=None,            # not modeled
                last_renewed_at=None,            # not modeled
                quotation_requested_at=r.requested_at,
                requested_preparation_date=r.request_due_date,
                quote_status=str(r.quote_status.value if hasattr(r.quote_status, "value") else r.quote_status),
                offer_status=str(r.offer_status.value if hasattr(r.offer_status, "value") else r.offer_status),
            )
        )
    return out
