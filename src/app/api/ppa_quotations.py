# src/app/api/ppa_quotations.py
from __future__ import annotations

from datetime import date, datetime, timedelta
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

router = APIRouter(prefix="/ppa_quotations", tags=["ppa_quotations"])


# ---------------------- mappings & helpers ---------------------- #

AREA_REGION_MAP = {
    "HOKKAIDO": (1, "Hokkaido", "北海道"),
    "TOHOKU":   (2, "Tohoku",   "東北"),
    "KANTO":    (3, "Tokyo",    "東京"),
    "CHUBU":    (4, "Chubu",    "中部"),
    "KANSAI":   (5, "Kansai",   "関西"),
    "CHUGOKU":  (6, "Chugoku",  "中国"),
    "SHIKOKU":  (7, "Shikoku",  "四国"),
    "KYUSHU":   (8, "Kyushu",   "九州"),
}

# Map your internal QuoteStatus -> BizQ-like triplet (id, en, jp)
PRICING_STATUS_MAP = {
    "draft":       (1, "pending",     "保留中"),
    "submitted":   (1, "pending",     "保留中"),
    "priced":      (2, "preliminary", "暫定"),
    "excel_ready": (3, "final",       "確定"),
}

# Map your internal OfferStatus -> BizQ-like triplet (id, en, jp)
OFFER_STATUS_MAP = {
    "none":    (1, "pending", "保留中"),
    "offered": (2, "offered", "提示済み"),
    "won":     (3, "won",     "受注"),
    "lost":    (4, "lost",    "失注"),
}


def region_from_area(area: Optional[str]) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    if not area:
        return (None, None, None)
    return AREA_REGION_MAP.get(area.upper(), (None, area, area))


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


def _fmt_last_updated(dt: Optional[datetime]) -> str:
    if isinstance(dt, (datetime, )):
        return dt.strftime("%Y-%m-%d %H:%M")
    return "—"


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
    # base aggregates
    sp_count = func.count(PpaSupplyPoint.id).label("sp_count")
    sum_kw = func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw")
    proj_count = func.count(sa.distinct(PpaProject.id)).label("project_count")

    stmt = (
        sa.select(
            PpaBundle.id.label("bundle_id"),
            Plan.id.label("plan_id"),
            Plan.name.label("plan_name_en"),
            Plan.name.label("plan_name_jp"),
            Customer.name.label("customer_name"),
            Agency.id.label("sales_agent_id"),
            Agency.name.label("sales_agent_name"),
            PpaBundle.area.label("area"),
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

    # filters
    if customer_id is not None:
        stmt = stmt.where(PpaBundle.customer_id == customer_id)
    if agency_id is not None:
        stmt = stmt.where(PpaBundle.agency_id == agency_id)
    if region:
        stmt = stmt.where(PpaBundle.area == region)

    # totals
    total_q = sa.select(func.count()).select_from(PpaBundle)
    total_count = (await session.execute(total_q)).scalar_one()

    # filtered totals (count distinct bundles produced by the grouped query)
    filtered_q = sa.select(func.count()).select_from(stmt.subquery())
    filtered_count = (await session.execute(filtered_q)).scalar_one()

    # sorting (safe map)
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
        # region mapping
        region_id, region_en, region_jp = region_from_area(r.area)

        # pricing/offer status mapping
        qs = (str(r.quote_status) or "").lower()
        ps_id, ps_en, ps_jp = PRICING_STATUS_MAP.get(qs, (1, "pending", "保留中"))

        os = (str(r.offer_status) or "").lower()
        os_id, os_en, os_jp = OFFER_STATUS_MAP.get(os, (1, "pending", "保留中"))

        # validity label and expiration date
        label, exp_date = _format_quote_valid_until(r.requested_at, r.quote_valid_days)

        item = PpaQuotationListItem(
            id=r.bundle_id,
            tender_number=_summary_number(r.bundle_id),
            customer_name=r.customer_name,
            plan_id=r.plan_id,
            plan_name_en=r.plan_name_en,
            plan_name_jp=r.plan_name_jp,
            sales_agent_id=r.sales_agent_id,
            sales_agent_name=r.sales_agent_name,
            region_id=region_id,
            region_name_en=region_en,
            region_name_jp=region_jp,
            quote_request_date=r.requested_at,
            last_date_for_quotation=r.request_due_date,
            quote_valid_until=label,
            contract_start_date=r.contract_start_date,
            num_of_spids=int(r.sp_count or 0),
            peak_demand=None,
            annual_usage=None,
            pricing_status_id=ps_id,
            pricing_status_en=ps_en,
            pricing_status_jp=ps_jp,
            offer_status_id=os_id,
            offer_status_en=os_en,
            offer_status_jp=os_jp,
            last_updated=_fmt_last_updated(r.updated_at),
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
    Requires: PpaSupplyPoint.project_id exists in model and DB.
    """
    # header aggregates across the bundle
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
            PpaBundle.area.label("area"),
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

    # region mapping
    region_id, region_en, region_jp = region_from_area(hdr_row.area)

    # pricing/offer status mapping
    qs = (str(hdr_row.quote_status) or "").lower()
    ps_id, ps_en, ps_jp = PRICING_STATUS_MAP.get(qs, (1, "pending", "保留中"))

    os = (str(hdr_row.offer_status) or "").lower()
    os_id, os_en, os_jp = OFFER_STATUS_MAP.get(os, (1, "pending", "保留中"))

    # validity label and expiration date
    label, exp_date = _format_quote_valid_until(hdr_row.requested_at, hdr_row.quote_valid_days)

    # per-project aggregation (capacity_mw + sp count + sum kw)
    # NOTE: requires PpaSupplyPoint.project_id column in DB and model.
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
        region_id=region_id,
        region_name_en=region_en,
        region_name_jp=region_jp,
        quote_request_date=hdr_row.requested_at,
        last_date_for_quotation=hdr_row.request_due_date,
        quote_valid_until=label,
        contract_start_date=hdr_row.contract_start_date,
        num_of_spids=int(hdr_row.sp_count or 0),
        peak_demand=None,
        annual_usage=None,
        pricing_status_id=ps_id,
        pricing_status_en=ps_en,
        pricing_status_jp=ps_jp,
        offer_status_id=os_id,
        offer_status_en=os_en,
        offer_status_jp=os_jp,
        last_updated=_fmt_last_updated(hdr_row.updated_at),
        has_quotation_file=False,
        summary_number=_summary_number(hdr_row.bundle_id),
        project_count=len(projects),
        contract_power_kw=float(hdr_row.sum_kw or 0.0),
        expiration_date=exp_date,
        projects=projects,
    )
    return detail
