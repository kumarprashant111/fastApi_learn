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
from app.schemas_projects import (
    ProjectListRow,
    QuotationListItem,
    QuotationListResponse,
)

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
):
    """
    Lists PPA bundles/projects with counts and totals.
    Uses a typed empty array literal to avoid NullType() in array_agg.
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
                annual_usage_kwh=0.0,  # placeholder until usage exists
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


@router.get("/ppa-quotations", response_model=QuotationListResponse)
async def list_ppa_quotations(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    rows: int = Query(100, ge=1, le=500),
    sort_by: str = Query("updated_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    customer_id: Optional[int] = None,
    agency_id: Optional[int] = None,
    area: Optional[str] = None,
    quote_status: Optional[str] = None,
    offer_status: Optional[str] = None,
):
    """
    BizQ-like list for PPA quotations (safe version).
    Only uses the tables you already have; unknown fields are left None/defaults.
    """

    def apply_filters(stmt):
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
        return stmt

    # counts
    total_count = (await session.scalar(sa.select(func.count()).select_from(PpaBundle))) or 0
    filtered_count = (
        await session.scalar(apply_filters(sa.select(func.count()).select_from(PpaBundle)))
    ) or 0

    # main query
    empty_int_array = sa.text("ARRAY[]::int[]")
    proj_ids_expr = func.coalesce(
        sa.cast(func.array_agg(sa.distinct(PpaProject.id)), pg.ARRAY(sa.Integer)),
        empty_int_array,
    ).label("proj_ids")

    base = (
        sa.select(
            PpaBundle.id.label("bundle_id"),
            Customer.name.label("customer_name"),
            Plan.id.label("plan_id"),
            Plan.name.label("plan_name"),
            Agency.id.label("agency_id"),
            Agency.name.label("agency_name"),
            PpaBundle.area,
            PpaBundle.requested_at.label("quote_request_date"),
            PpaBundle.request_due_date.label("last_date_for_quotation"),
            PpaBundle.contract_start_date,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
            func.count(PpaSupplyPoint.id).label("sp_count"),
            func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw"),
            proj_ids_expr,
            PpaBundle.updated_at.label("updated_at"),
        )
        .join(Plan, Plan.id == PpaBundle.plan_id)
        .join(Customer, Customer.id == PpaBundle.customer_id)
        .outerjoin(Agency, Agency.id == PpaBundle.agency_id)
        .outerjoin(PpaSupplyPoint, PpaSupplyPoint.bundle_id == PpaBundle.id)
        .outerjoin(PpaProject, PpaProject.bundle_id == PpaBundle.id)
        .group_by(
            PpaBundle.id,
            Customer.name,
            Plan.id, Plan.name,
            Agency.id, Agency.name,
            PpaBundle.area,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.contract_start_date,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
            PpaBundle.updated_at,
        )
    )

    # sort support
    sort_map = {
        "updated_at": "updated_at",
        "quote_request_date": "quote_request_date",
        "contract_start_date": "contract_start_date",
        "id": "bundle_id",
    }
    sort_col = sort_map.get(sort_by, "updated_at")
    sort_expr = sa.text(f"{sort_col} {sort_order}")

    page_stmt = apply_filters(base).order_by(sort_expr).limit(rows).offset((page - 1) * rows)
    result = (await session.execute(page_stmt)).all()

    # shape response
    data: List[QuotationListItem] = []
    for r in result:
        tender = f"BQ{r.bundle_id:011d}"  # fabricate tender number
        plan_name_en = r.plan_name
        plan_name_jp = r.plan_name
        last_updated = r.updated_at.strftime("%Y-%m-%d %H:%M") if r.updated_at else None

        data.append(
            QuotationListItem(
                id=r.bundle_id,
                tender_number=tender,
                customer_name=r.customer_name,
                plan_id=r.plan_id,
                plan_name_en=plan_name_en,
                plan_name_jp=plan_name_jp,
                sales_agent_id=r.agency_id,
                sales_agent_name=r.agency_name,
                region_id=None,
                region_name_en=None,
                region_name_jp=None,
                quote_request_date=r.quote_request_date.isoformat() if r.quote_request_date else None,
                last_date_for_quotation=r.last_date_for_quotation.isoformat()
                if r.last_date_for_quotation
                else None,
                quote_valid_until=None,
                contract_start_date=r.contract_start_date.isoformat() if r.contract_start_date else None,
                num_of_spids=int(r.sp_count or 0),
                peak_demand=None,
                annual_usage=None,
                pricing_status_id=None,
                pricing_status_en=str(r.quote_status) if r.quote_status is not None else None,
                pricing_status_jp=str(r.quote_status) if r.quote_status is not None else None,
                offer_status_id=None,
                offer_status_en=str(r.offer_status) if r.offer_status is not None else None,
                offer_status_jp=str(r.offer_status) if r.offer_status is not None else None,
                last_updated=last_updated,
                has_quotation_file=False,
            )
        )

    return QuotationListResponse(
        total_count=int(total_count),
        filtered_count=int(filtered_count),
        data=data,
    )
