# src/app/api/ppa_quotations.py
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, List, Tuple

from fastapi import APIRouter, Depends, Query, HTTPException
import sqlalchemy as sa
from sqlalchemy import func, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import (
    PpaBundle,
    PpaProject,
    PpaSupplyPoint,
    Plan,
    Customer,
    Agency,
)
from app.schemas_ppa_quotations import (
    PpaQuotationListResponse,
    PpaQuotationListItem,
    PpaQuotationDetail,
    PpaQuotationDetailProject,
)

router = APIRouter(prefix="/ppa_quotations", tags=["projects"])


# ---------------------- helpers ---------------------- #

def _format_quote_valid_until(requested_at: Optional[date], days: Optional[int]) -> Tuple[str, Optional[date]]:
    """
    Return ('YYYY-MM-DD (N日)', expiration_date) given a base date and a validity window in days.
    If requested_at or days is None, returns ('', None).
    """
    if not requested_at or not days:
        return ("", None)
    exp = requested_at + timedelta(days=int(days))
    label = f"{exp.strftime('%Y-%m-%d')} ({int(days)}日)"
    return (label, exp)


def _summary_number(bundle_id: int) -> str:
    # Change the prefix/width if you prefer a different display format.
    return f"PPA{bundle_id:08d}"


# ---------------------- list endpoint ---------------------- #

@router.get("", response_model=PpaQuotationListResponse)
async def list_ppa_quotations(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    rows: int = Query(20, ge=1, le=200),
    sort_by: Optional[str] = Query("updated_at"),
    sort_order: Optional[str] = Query("desc"),
    # simple filters you can extend later
    customer_id: Optional[int] = None,
    agency_id: Optional[int] = None,
    region: Optional[str] = None,
):
    """
    BizQ-like list with a couple of extra PPA fields (summary_number, project_count, contract_power_kw, expiration_date).
    """
    # base sub-select to compute counts and totals
    sp_count = func.count(PpaSupplyPoint.id).label("sp_count")
    sum_kw = func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw")
    proj_count = func.count(sa.distinct(PpaProject.id)).label("project_count")

    stmt = (
        sa.select(
            PpaBundle.id.label("bundle_id"),                          # <-- real column
            Plan.id.label("plan_id"),
            Plan.name.label("plan_name_en"),
            Plan.name.label("plan_name_jp"),
            Customer.name.label("customer_name"),
            Agency.id.label("sales_agent_id"),
            Agency.name.label("sales_agent_name"),
            PpaBundle.area.label("region_name_en"),
            PpaBundle.area.label("region_name_jp"),
            PpaBundle.requested_at.label("requested_at"),
            PpaBundle.request_due_date.label("request_due_date"),
            PpaBundle.quote_valid_days.label("quote_valid_days"),
            PpaBundle.contract_start_date.label("contract_start_date"),
            PpaBundle.quote_status.label("quote_status"),
            PpaBundle.offer_status.label("offer_status"),
            PpaBundle.updated_at.label("updated_at"),
            sp_count,
            sum_kw,
            proj_count,
        )
        .join(Plan, Plan.id == PpaBundle.plan_id)
        .join(Customer, Customer.id == PpaBundle.customer_id)
        .outerjoin(Agency, Agency.id == PpaBundle.agency_id)
        .outerjoin(PpaProject, PpaProject.bundle_id == PpaBundle.id)
        .outerjoin(PpaSupplyPoint, PpaSupplyPoint.bundle_id == PpaBundle.id)
        .group_by(
            PpaBundle.id,
            Plan.id, Plan.name,
            Customer.name,
            Agency.id, Agency.name,
            PpaBundle.area,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.quote_valid_days,
            PpaBundle.contract_start_date,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
            PpaBundle.updated_at,
        )
    )

    if customer_id is not None:
        stmt = stmt.where(PpaBundle.customer_id == customer_id)
    if agency_id is not None:
        stmt = stmt.where(PpaBundle.agency_id == agency_id)
    if region:
        stmt = stmt.where(PpaBundle.area == region)

    # totals
    total_q = sa.select(func.count()).select_from(PpaBundle)
    total_count = (await session.execute(total_q)).scalar_one()

    # filtered totals (count distinct bundles in the list query)
    filtered_q = sa.select(func.count()).select_from(stmt.subquery())
    filtered_count = (await session.execute(filtered_q)).scalar_one()

    # sorting
    sort_map = {
        "updated_at": literal_column("updated_at"),
        "contract_start_date": literal_column("contract_start_date"),
        "customer_name": literal_column("customer_name"),
    }
    sort_col = sort_map.get((sort_by or "").lower(), literal_column("updated_at"))
    if (sort_order or "").lower() == "asc":
        stmt = stmt.order_by(sort_col.asc())
    else:
        stmt = stmt.order_by(sort_col.desc())

    # paging
    stmt = stmt.limit(rows).offset((page - 1) * rows)

    rows_ = (await session.execute(stmt)).all()

    data: List[PpaQuotationListItem] = []
    for r in rows_:
        # map quote_valid_until label & expiration_date
        label, exp_date = _format_quote_valid_until(r.requested_at, r.quote_valid_days)

        item = PpaQuotationListItem(
            id=r.bundle_id,
            tender_number=_summary_number(r.bundle_id),   # show same on both fields for now
            customer_name=r.customer_name,
            plan_id=r.plan_id,
            plan_name_en=r.plan_name_en,
            plan_name_jp=r.plan_name_jp,
            sales_agent_id=r.sales_agent_id,
            sales_agent_name=r.sales_agent_name,
            region_id=None,  # not modeled separately
            region_name_en=r.region_name_en,
            region_name_jp=r.region_name_jp,
            quote_request_date=r.requested_at,
            last_date_for_quotation=r.request_due_date,
            quote_valid_until=label,
            contract_start_date=r.contract_start_date,
            num_of_spids=int(r.sp_count or 0),
            peak_demand=None,
            annual_usage=None,
            pricing_status_id=1 if str(r.quote_status or "").lower() in ("pending", "draft", "") else 2,
            pricing_status_en=str(r.quote_status or "pending").lower(),
            pricing_status_jp="保留中" if str(r.quote_status or "").lower() in ("pending", "draft", "") else "暫定",
            offer_status_id=1 if str(r.offer_status or "").lower() in ("pending", "") else 2,
            offer_status_en=str(r.offer_status or "pending").lower(),
            offer_status_jp="保留中" if str(r.offer_status or "").lower() in ("pending", "") else "確定",
            last_updated=(r.updated_at or date.today()).strftime("%Y-%m-%d %H:%M") if hasattr(r.updated_at, "strftime") else "—",
            has_quotation_file=False,
            summary_number=_summary_number(r.bundle_id),
            project_count=int(r.project_count or 0),
            contract_power_kw=float(r.sum_kw or 0.0),
            expiration_date=exp_date,
        )
        data.append(item)

    return PpaQuotationListResponse(
        total_count=int(total_count or 0),
        filtered_count=int(filtered_count or 0),
        data=data,
    )


# ---------------------- detail endpoint ---------------------- #

@router.get("/{bundle_id}", response_model=PpaQuotationDetail)
async def get_ppa_quotation_detail(
    bundle_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Header info for the bundle + per-project aggregation (capacity split).
    """
    # header
    sp_count = func.count(PpaSupplyPoint.id).label("sp_count")
    sum_kw = func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw")

    hdr_stmt = (
        sa.select(
            PpaBundle.id.label("bundle_id"),
            Plan.id.label("plan_id"),
            Plan.name.label("plan_name_en"),
            Plan.name.label("plan_name_jp"),
            Customer.name.label("customer_name"),
            Agency.id.label("sales_agent_id"),
            Agency.name.label("sales_agent_name"),
            PpaBundle.area.label("region_name_en"),
            PpaBundle.area.label("region_name_jp"),
            PpaBundle.requested_at.label("requested_at"),
            PpaBundle.request_due_date.label("request_due_date"),
            PpaBundle.quote_valid_days.label("quote_valid_days"),
            PpaBundle.contract_start_date.label("contract_start_date"),
            PpaBundle.quote_status.label("quote_status"),
            PpaBundle.offer_status.label("offer_status"),
            PpaBundle.updated_at.label("updated_at"),
            sp_count,
            sum_kw,
        )
        .join(Plan, Plan.id == PpaBundle.plan_id)
        .join(Customer, Customer.id == PpaBundle.customer_id)
        .outerjoin(Agency, Agency.id == PpaBundle.agency_id)
        .outerjoin(PpaProject, PpaProject.bundle_id == PpaBundle.id)
        .outerjoin(PpaSupplyPoint, PpaSupplyPoint.bundle_id == PpaBundle.id)
        .where(PpaBundle.id == bundle_id)
        .group_by(
            PpaBundle.id,
            Plan.id, Plan.name,
            Customer.name,
            Agency.id, Agency.name,
            PpaBundle.area,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.quote_valid_days,
            PpaBundle.contract_start_date,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
            PpaBundle.updated_at,
        )
    )

    hdr_row = (await session.execute(hdr_stmt)).first()
    if not hdr_row:
        raise HTTPException(status_code=404, detail="Bundle not found")

    label, exp_date = _format_quote_valid_until(hdr_row.requested_at, hdr_row.quote_valid_days)

    # per-project aggregation (capacity_mw + sp count + sum kw)
    proj_stmt = (
        sa.select(
            PpaProject.id.label("project_id"),
            PpaProject.capacity_mw.label("capacity_mw"),
            func.count(PpaSupplyPoint.id).label("sp_count"),
            func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw"),
        )
        .outerjoin(PpaSupplyPoint, PpaSupplyPoint.project_id == PpaProject.id)
        .where(PpaProject.bundle_id == bundle_id)
        .group_by(PpaProject.id, PpaProject.capacity_mw)
        .order_by(PpaProject.id)
    )
    proj_rows = (await session.execute(proj_stmt)).all()

    projects: List[PpaQuotationDetailProject] = []
    for r in proj_rows:
        projects.append(
            PpaQuotationDetailProject(
                project_id=r.project_id,
                capacity_mw=float(r.capacity_mw) if r.capacity_mw is not None else None,
                num_of_spids=int(r.sp_count or 0),
                contract_power_kw=float(r.sum_kw or 0.0),
            )
        )

    detail = PpaQuotationDetail(
        id=hdr_row.bundle_id,
        tender_number=_summary_number(hdr_row.bundle_id),
        customer_name=hdr_row.customer_name,
        plan_id=hdr_row.plan_id,
        plan_name_en=hdr_row.plan_name_en,
        plan_name_jp=hdr_row.plan_name_jp,
        sales_agent_id=hdr_row.sales_agent_id,
        sales_agent_name=hdr_row.sales_agent_name,
        region_id=None,
        region_name_en=hdr_row.region_name_en,
        region_name_jp=hdr_row.region_name_jp,
        quote_request_date=hdr_row.requested_at,
        last_date_for_quotation=hdr_row.request_due_date,
        quote_valid_until=label,
        contract_start_date=hdr_row.contract_start_date,
        num_of_spids=int(hdr_row.sp_count or 0),
        peak_demand=None,
        annual_usage=None,
        pricing_status_id=1 if str(hdr_row.quote_status or "").lower() in ("pending", "draft", "") else 2,
        pricing_status_en=str(hdr_row.quote_status or "pending").lower(),
        pricing_status_jp="保留中" if str(hdr_row.quote_status or "").lower() in ("pending", "draft", "") else "暫定",
        offer_status_id=1 if str(hdr_row.offer_status or "").lower() in ("pending", "") else 2,
        offer_status_en=str(hdr_row.offer_status or "pending").lower(),
        offer_status_jp="保留中" if str(hdr_row.offer_status or "").lower() in ("pending", "") else "確定",
        last_updated=(hdr_row.updated_at or date.today()).strftime("%Y-%m-%d %H:%M") if hasattr(hdr_row.updated_at, "strftime") else "—",
        has_quotation_file=False,
        summary_number=_summary_number(hdr_row.bundle_id),
        project_count=len(projects),
        contract_power_kw=float(hdr_row.sum_kw or 0.0),
        expiration_date=exp_date,
        projects=projects,
    )
    return detail
