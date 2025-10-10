# src/app/api/projects.py
from __future__ import annotations
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects import postgresql as pg

from app.db import get_session
from app.models import (
    PpaBundle, PpaProject, PpaSupplyPoint, Plan, Customer, Agency
)
from app.schemas_ppa_quotations import ProjectListRow


# Renamed section + base path
router = APIRouter(prefix="/ppa_quotations", tags=["ppa_quotations"])


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
):
    """
    Lists PPA bundles/projects with counts and totals.

    Note:
    - We use a typed empty array literal (ARRAY[]::int[]) so COALESCE on
      array_agg(DISTINCT ppa_projects.id) never produces a NullType.
    """
    empty_int_array = sa.text("ARRAY[]::int[]")

    proj_ids_expr = func.coalesce(
        sa.cast(func.array_agg(sa.distinct(PpaProject.id)), pg.ARRAY(sa.Integer)),
        empty_int_array,
    ).label("proj_ids")

    stmt = (
        sa.select(
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
            proj_ids_expr,
        )
        .join(Plan, Plan.id == PpaBundle.plan_id)
        .join(Customer, Customer.id == PpaBundle.customer_id)
        .outerjoin(Agency, Agency.id == PpaBundle.agency_id)
        .outerjoin(PpaSupplyPoint, PpaSupplyPoint.bundle_id == PpaBundle.id)
        .outerjoin(PpaProject, PpaProject.bundle_id == PpaBundle.id)
        .group_by(
            PpaBundle.id, Plan.name, Customer.name, Agency.name,
            PpaBundle.area, PpaBundle.contract_start_date,
            PpaBundle.requested_at, PpaBundle.request_due_date,
            PpaBundle.quote_status, PpaBundle.offer_status,
        )
        .order_by(PpaBundle.id.desc())
        .limit(size)
        .offset((page - 1) * size)
    )

    # Filters
    if customer_id is not None:
        stmt = stmt.where(PpaBundle.customer_id == customer_id)
    if agency_id is not None:
        stmt = stmt.where(PpaBundle.agency_id == agency_id)
    if area:
        stmt = stmt.where(PpaBundle.area == area)
    if quote_status:
        stmt = stmt.where(PpaBundle.quote_status == quote_status)
    if offer_status:
        stmt = stmt.where(PpaBundle.offer_status == offer_status)

    rows = (await session.execute(stmt)).all()

    out: List[ProjectListRow] = []
    for r in rows:
        proj_ids: List[int] = [int(pid) for pid in (r.proj_ids or []) if pid is not None]
        out.append(
            ProjectListRow(
                id=r.bundle_id,
                project_numbers=proj_ids,
                plan=r.plan_name,
                customer=r.customer_name,
                agency=r.agency_name,
                area=r.area,
                supply_point_count=int(r.sp_count or 0),
                contracted_power_kw=float(r.sum_kw or 0.0),
                annual_usage_kwh=0.0,  # placeholder until usage table exists
                contract_start_date=r.contract_start_date,
                expiration_date=None,
                last_renewed_at=None,
                quotation_requested_at=r.requested_at,
                requested_preparation_date=r.request_due_date,
                quote_status=str(r.quote_status) if r.quote_status is not None else None,
                offer_status=str(r.offer_status) if r.offer_status is not None else None,
            )
        )
    return out
