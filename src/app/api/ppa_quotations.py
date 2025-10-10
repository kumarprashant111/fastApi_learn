# src/app/api/ppa_quotations.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
import sqlalchemy as sa
from sqlalchemy import func
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
    PpaQuotationListItem,
    PpaQuotationListResponse,
    PpaQuotationProject,
    PpaQuotationDetail,
)

router = APIRouter(prefix="/ppa_quotations", tags=["ppa_quotations"])


# -------------------------------
# Helpers
# -------------------------------

def _region_from_area(area: Optional[str]) -> tuple[int, str, str]:
    """
    Very lightweight area->region mapping until you model a Regions table.
    """
    if not area:
        return 0, "Unknown", "不明"
    a = area.upper()
    mapping = {
        "TOKYO": (3, "Tokyo", "東京"),
        "KANTO": (3, "Tokyo", "東京"),
        "TOHOKU": (2, "Tohoku", "東北"),
        "KANSAI": (4, "Kansai", "関西"),
        "CHUBU": (5, "Chubu", "中部"),
        "HOKKAIDO": (1, "Hokkaido", "北海道"),
        "KYUSHU": (9, "Kyushu", "九州"),
        "CHUGOKU": (6, "Chugoku", "中国"),
        "SHIKOKU": (7, "Shikoku", "四国"),
        "HOKURIKU": (8, "Hokuriku", "北陸"),
    }
    return mapping.get(a, (3, "Tokyo", "東京"))


def _format_quote_valid_until(base: Optional[date], days: Optional[int]) -> tuple[Optional[str], Optional[date]]:
    """
    Compute (display_label, expiration_date) purely in Python.
    - display_label example: "2025-11-02 (30日)"
    """
    if not base or not days:
        return None, None
    d = int(days)
    exp = base + timedelta(days=d)
    return f"{exp:%Y-%m-%d} ({d}日)", exp


def _tender_number(bundle_id: int) -> str:
    return f"PPA{bundle_id:08d}"


# -------------------------------
# List endpoint (BizQ-like envelope)
# -------------------------------

@router.get("", response_model=PpaQuotationListResponse)
async def list_ppa_quotations(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    rows: int = Query(20, ge=1, le=200),
    sort_by: str = Query("updated_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    customer_id: Optional[int] = None,
    agency_id: Optional[int] = None,
    region: Optional[str] = None,   # optional text filter - maps to area
    quote_status: Optional[str] = None,
    offer_status: Optional[str] = None,
):
    """
    Returns:
      {
        "total_count": <all bundles count>,
        "filtered_count": <count after filters>,
        "data": [ PpaQuotationListItem, ... ]
      }
    """
    # total_count (no filters)
    total_stmt = sa.select(func.count(PpaBundle.id))
    total_count = (await session.execute(total_stmt)).scalar_one()

    # base selectable
    stmt = (
        sa.select(
            PpaBundle.id.label("bundle_id"),
            Plan.id.label("plan_id"),
            Plan.name.label("plan_name"),
            Customer.name.label("customer_name"),
            Agency.id.label("agency_id"),
            Agency.name.label("agency_name"),
            PpaBundle.area,
            PpaBundle.contract_start_date,
            PpaBundle.requested_at,          # quote_request_date
            PpaBundle.request_due_date,      # last_date_for_quotation
            PpaBundle.quote_valid_days,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
            PpaBundle.updated_at.label("last_updated"),
            func.count(sa.distinct(PpaProject.id)).label("project_count"),
            func.count(sa.distinct(PpaSupplyPoint.id)).label("sp_count"),
            func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw"),
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
            PpaBundle.contract_start_date,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.quote_valid_days,
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
        # simple contains on area name
        stmt = stmt.where(PpaBundle.area.ilike(f"%{region}%"))
    if quote_status:
        stmt = stmt.where(PpaBundle.quote_status == quote_status)
    if offer_status:
        stmt = stmt.where(PpaBundle.offer_status == offer_status)

    # filtered count (subquery over bundle ids)
    filtered_count_stmt = sa.select(func.count()).select_from(
        sa.select(PpaBundle.id)
        .join(Plan, Plan.id == PpaBundle.plan_id)
        .join(Customer, Customer.id == PpaBundle.customer_id)
        .outerjoin(Agency, Agency.id == PpaBundle.agency_id)
        .outerjoin(PpaProject, PpaProject.bundle_id == PpaBundle.id)
        .outerjoin(PpaSupplyPoint, PpaSupplyPoint.bundle_id == PpaBundle.id)
        .group_by(PpaBundle.id)
        .where(True)  # placeholder to apply same filters
    )

    # Rebuild the same filters for the filtered_count subquery
    filters: List[sa.ClauseElement] = []
    if customer_id is not None:
        filters.append(PpaBundle.customer_id == customer_id)
    if agency_id is not None:
        filters.append(PpaBundle.agency_id == agency_id)
    if region:
        filters.append(PpaBundle.area.ilike(f"%{region}%"))
    if quote_status:
        filters.append(PpaBundle.quote_status == quote_status)
    if offer_status:
        filters.append(PpaBundle.offer_status == offer_status)

    if filters:
        filtered_count_stmt = filtered_count_stmt.where(sa.and_(*filters))

    filtered_count = (await session.execute(filtered_count_stmt)).scalar_one()

    # sorting
    sort_col_map = {
        "updated_at": "last_updated",
        "quote_request_date": "requested_at",
        "contract_start_date": "contract_start_date",
        "customer_name": "customer_name",
        "plan_name": "plan_name",
    }
    sort_col = sort_col_map.get(sort_by, "last_updated")
    sort_expr = sa.text(f"{sort_col} {sort_order}")
    stmt = stmt.order_by(sort_expr)

    # pagination
    stmt = stmt.limit(rows).offset((page - 1) * rows)

    rows_rs = (await session.execute(stmt)).all()

    items: List[PpaQuotationListItem] = []
    for r in rows_rs:
        region_id, region_name_en, region_name_jp = _region_from_area(r.area)
        tender = _tender_number(int(r.bundle_id))
        qv_label, exp_date = _format_quote_valid_until(r.requested_at, r.quote_valid_days)

        items.append(
            PpaQuotationListItem(
                id=int(r.bundle_id),
                tender_number=tender,
                customer_name=r.customer_name,
                plan_id=int(r.plan_id),
                plan_name_en=r.plan_name,
                plan_name_jp=r.plan_name,   # same until you have JP label
                sales_agent_id=int(r.agency_id) if r.agency_id is not None else None,
                sales_agent_name=r.agency_name,
                region_id=region_id,
                region_name_en=region_name_en,
                region_name_jp=region_name_jp,
                quote_request_date=r.requested_at,
                last_date_for_quotation=r.request_due_date,
                quote_valid_until=qv_label,
                contract_start_date=r.contract_start_date,
                num_of_spids=int(r.sp_count or 0),
                peak_demand=None,     # not modeled yet
                annual_usage=None,    # not modeled yet
                pricing_status_id=1,  # static placeholder like BizQ "pending"
                pricing_status_en="pending",
                pricing_status_jp="保留中",
                offer_status_id=1,    # static placeholder like BizQ "pending"
                offer_status_en="pending",
                offer_status_jp="保留中",
                last_updated=r.last_updated.strftime("%Y-%m-%d %H:%M") if isinstance(r.last_updated, datetime) else None,
                has_quotation_file=False,
                # Extra columns requested for PPA view
                summary_number=tender,                       # = tender_number for display
                project_count=int(r.project_count or 0),     # 案件数 (per summary)
                contract_power_kw=float(r.sum_kw or 0.0),    # 契約電力 (sum of SP.contract_kw)
                expiration_date=exp_date,                    # 有効期限
            )
        )

    return PpaQuotationListResponse(
        total_count=int(total_count),
        filtered_count=int(filtered_count),
        data=items,
    )


# -------------------------------
# Detail endpoint
# -------------------------------

@router.get("/{bundle_id}", response_model=PpaQuotationDetail)
async def get_ppa_quotation_detail(
    bundle_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Detail view for a single PPA bundle (まとめ番号＝bundle).
    Returns header info + list of projects (案件番号) under that bundle.

    Note:
    - PpaSupplyPoint doesn't have project_id in your schema, so per-project
      supply-point counts are not available. We still provide bundle-level SP
      totals and per-project capacity/IDs neatly.
    """
    # Header / bundle row
    head_stmt = (
        sa.select(
            PpaBundle.id.label("bundle_id"),
            Plan.id.label("plan_id"),
            Plan.name.label("plan_name"),
            Customer.name.label("customer_name"),
            Agency.id.label("agency_id"),
            Agency.name.label("agency_name"),
            PpaBundle.area,
            PpaBundle.contract_start_date,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.quote_valid_days,
            PpaBundle.updated_at.label("last_updated"),
            func.count(sa.distinct(PpaProject.id)).label("project_count"),
            func.count(sa.distinct(PpaSupplyPoint.id)).label("sp_count"),
            func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw"),
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
            PpaBundle.contract_start_date,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.quote_valid_days,
            PpaBundle.updated_at,
        )
    )
    head_row = (await session.execute(head_stmt)).one_or_none()
    if not head_row:
        raise HTTPException(status_code=404, detail="Bundle not found")

    r = head_row
    region_id, region_name_en, region_name_jp = _region_from_area(r.area)
    tender = _tender_number(int(r.bundle_id))
    qv_label, exp_date = _format_quote_valid_until(r.requested_at, r.quote_valid_days)

    # Projects under this bundle
    proj_stmt = (
        sa.select(
            PpaProject.id.label("project_id"),
            PpaProject.capacity_mw.label("capacity_mw"),
        )
        .where(PpaProject.bundle_id == bundle_id)
        .order_by(PpaProject.id.asc())
    )
    proj_rows = (await session.execute(proj_stmt)).all()

    projects: List[PpaQuotationProject] = []
    for pr in proj_rows:
        projects.append(
            PpaQuotationProject(
                project_id=int(pr.project_id),
                capacity_mw=float(pr.capacity_mw or 0.0),
                # num_of_spids: not available per project (no project_id on PpaSupplyPoint)
                num_of_spids=None,
                contract_power_kw=None,
            )
        )

    detail = PpaQuotationDetail(
        id=int(r.bundle_id),
        tender_number=tender,
        customer_name=r.customer_name,
        plan_id=int(r.plan_id),
        plan_name_en=r.plan_name,
        plan_name_jp=r.plan_name,
        sales_agent_id=int(r.agency_id) if r.agency_id is not None else None,
        sales_agent_name=r.agency_name,
        region_id=region_id,
        region_name_en=region_name_en,
        region_name_jp=region_name_jp,
        quote_request_date=r.requested_at,
        last_date_for_quotation=r.request_due_date,
        quote_valid_until=qv_label,
        contract_start_date=r.contract_start_date,
        num_of_spids=int(r.sp_count or 0),
        peak_demand=None,
        annual_usage=None,
        pricing_status_id=1,
        pricing_status_en="pending",
        pricing_status_jp="保留中",
        offer_status_id=1,
        offer_status_en="pending",
        offer_status_jp="保留中",
        last_updated=r.last_updated.strftime("%Y-%m-%d %H:%M") if isinstance(r.last_updated, datetime) else None,
        has_quotation_file=False,
        summary_number=tender,
        project_count=int(r.project_count or 0),
        contract_power_kw=float(r.sum_kw or 0.0),
        expiration_date=exp_date,
        projects=projects,
    )
    return detail
