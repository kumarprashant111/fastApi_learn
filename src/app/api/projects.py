# src/app/api/projects.py
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, Query
import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import (
    PpaBundle, PpaProject, PpaSupplyPoint, Plan, Customer, Agency
)
from app.schemas_projects import QuotationListItem, QuotationListResponse

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("/ppa-quotations", response_model=QuotationListResponse, summary="List Ppa Quotations")
async def list_ppa_quotations(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    rows: int = Query(20, ge=1, le=200),
    sort_by: Optional[str] = Query("updated_at"),
    sort_order: Optional[str] = Query("desc"),  # "asc" | "desc"
    customer_id: Optional[int] = None,
    agency_id: Optional[int] = None,
    region: Optional[str] = None,               # maps to area
    pricing_status: Optional[str] = None,       # maps to quote_status
    offer_status: Optional[str] = None,
) -> QuotationListResponse:
    # Base query with aggregates per bundle
    sp_count = func.count(PpaSupplyPoint.id)
    sum_kw = func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0)
    proj_ids = func.array_remove(func.array_agg(sa.distinct(PpaProject.id)), None)

    stmt = (
        sa.select(
            PpaBundle.id.label("bundle_id"),
            PpaBundle.contract_start_date,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
            PpaBundle.area,
            Plan.id.label("plan_id"),
            Plan.name.label("plan_name"),
            Customer.name.label("customer_name"),
            Agency.id.label("agency_id"),
            Agency.name.label("agency_name"),
            sp_count.label("sp_count"),
            sum_kw.label("sum_kw"),
            proj_ids.label("proj_ids"),
            func.greatest(PpaBundle.updated_at, PpaBundle.created_at).label("last_updated"),
        )
        .join(Plan, Plan.id == PpaBundle.plan_id)
        .join(Customer, Customer.id == PpaBundle.customer_id)
        .outerjoin(Agency, Agency.id == PpaBundle.agency_id)
        .outerjoin(PpaSupplyPoint, PpaSupplyPoint.bundle_id == PpaBundle.id)
        .outerjoin(PpaProject, PpaProject.bundle_id == PpaBundle.id)
        .group_by(
            PpaBundle.id, PpaBundle.contract_start_date, PpaBundle.requested_at,
            PpaBundle.request_due_date, PpaBundle.quote_status, PpaBundle.offer_status,
            PpaBundle.area, Plan.id, Plan.name, Customer.name, Agency.id, Agency.name,
            PpaBundle.updated_at, PpaBundle.created_at,
        )
    )

    # Filters
    if customer_id is not None:
        stmt = stmt.where(PpaBundle.customer_id == customer_id)
    if agency_id is not None:
        stmt = stmt.where(PpaBundle.agency_id == agency_id)
    if region:
        stmt = stmt.where(PpaBundle.area == region)
    if pricing_status:
        stmt = stmt.where(PpaBundle.quote_status == pricing_status)
    if offer_status:
        stmt = stmt.where(PpaBundle.offer_status == offer_status)

    # Sorting
    sort_map = {
        "updated_at": sa.text("last_updated"),
        "quote_request_date": PpaBundle.requested_at,
        "last_date_for_quotation": PpaBundle.request_due_date,
        "contract_start_date": PpaBundle.contract_start_date,
        "customer_name": sa.text("customer_name"),
        "plan_name": sa.text("plan_name"),
        "region": sa.text("area"),
    }
    sort_col = sort_map.get(sort_by or "updated_at", sa.text("last_updated"))
    order_expr = sort_col.desc() if (sort_order or "desc").lower() == "desc" else sort_col.asc()
    stmt = stmt.order_by(order_expr).limit(rows).offset((page - 1) * rows)

    # Execute
    result = await session.execute(stmt)
    rows_data = result.all()

    # Total count (all bundles)
    total_count = await session.scalar(sa.select(func.count()).select_from(PpaBundle))
    # Filtered count (apply same filters without aggregates)
    filtered_stmt = sa.select(func.count()).select_from(PpaBundle)
    if customer_id is not None:
        filtered_stmt = filtered_stmt.where(PpaBundle.customer_id == customer_id)
    if agency_id is not None:
        filtered_stmt = filtered_stmt.where(PpaBundle.agency_id == agency_id)
    if region:
        filtered_stmt = filtered_stmt.where(PpaBundle.area == region)
    if pricing_status:
        filtered_stmt = filtered_stmt.where(PpaBundle.quote_status == pricing_status)
    if offer_status:
        filtered_stmt = filtered_stmt.where(PpaBundle.offer_status == offer_status)
    filtered_count = await session.scalar(filtered_stmt)

    # Build payload
    data = []
    for r in rows_data:
        tender_number = f"BQ{r.bundle_id:011d}"  # placeholder to mimic sample
        # Simple JP/EN copies for now; adjust later if you have i18n names
        plan_name_en = r.plan_name
        plan_name_jp = r.plan_name
        region_en = r.area
        region_jp = r.area

        data.append(
            QuotationListItem(
                id=r.bundle_id,
                tender_number=tender_number,
                customer_name=r.customer_name,
                plan_id=r.plan_id,
                plan_name_en=plan_name_en,
                plan_name_jp=plan_name_jp,
                sales_agent_id=r.agency_id,
                sales_agent_name=r.agency_name,
                region_id=None,
                region_name_en=region_en,
                region_name_jp=region_jp,
                quote_request_date=r.requested_at,
                last_date_for_quotation=r.request_due_date,
                quote_valid_until=None,  # derive if you add validity_days
                contract_start_date=r.contract_start_date,
                num_of_spids=int(r.sp_count or 0),
                peak_demand=None,
                annual_usage=None,
                pricing_status_id=None,
                pricing_status_en=str(r.quote_status) if r.quote_status else None,
                pricing_status_jp=str(r.quote_status) if r.quote_status else None,
                offer_status_id=None,
                offer_status_en=str(r.offer_status) if r.offer_status else None,
                offer_status_jp=str(r.offer_status) if r.offer_status else None,
                last_updated=r.last_updated,
                has_quotation_file=False,
            )
        )

    return QuotationListResponse(
        total_count=int(total_count or 0),
        filtered_count=int(filtered_count or 0),
        data=data,
    )
