# src/app/api/ppa_quotations.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Query, HTTPException

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
    PpaProjectBrief,
    PpaQuotationDetailResponse,
)

router = APIRouter(prefix="/ppa_quotations", tags=["ppa_quotations"])

# --- helpers --------------------------------------------------------------

def _status_maps() -> Tuple[dict, dict]:
    # Map your enum values to the BizQ wording
    pricing_map = {
        "DRAFT":        (1, "pending", "保留中"),
        "PRELIMINARY":  (2, "preliminary", "暫定"),
        "FINAL":        (3, "finalized", "確定"),
    }
    offer_map = {
        "NONE":     (1, "pending", "保留中"),
        "SENT":     (2, "sent", "送付済み"),
        "ACCEPTED": (3, "accepted", "受領"),
        "REJECTED": (4, "rejected", "拒否"),
    }
    return pricing_map, offer_map


def _region_from_area(area: Optional[str]) -> Tuple[int, str, str]:
    # Simple area→region mapping; adjust as needed
    if not area:
        return 0, "Unknown", "不明"
    area_up = area.upper()
    if area_up in {"KANTO", "TOKYO"}:
        return 3, "Tokyo", "東京"
    if area_up in {"TOHOKU"}:
        return 2, "Tohoku", "東北"
    return 1, area.title(), area  # generic fallback


def _summary_number(bundle_id: int) -> str:
    # Your BizQ shows like BQ2025..., here we keep the earlier PPA0000... scheme
    return f"PPA{bundle_id:08d}"


def _valid_until_string(req_date: Optional[date], days: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (quote_valid_until display, expiration_date yyyy-mm-dd)
    e.g. ("2025-08-30 (60日)", "2025-08-30")
    """
    if not req_date or not days:
        return None, None
    exp = req_date + timedelta(days=int(days))
    exp_str = exp.isoformat()
    return f"{exp_str} ({int(days)}日)", exp_str


# --- LIST --------------------------------------------------------------

@router.get("", response_model=PpaQuotationListResponse)
async def list_ppa_quotations(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    rows: int = Query(20, ge=1, le=200),
    sort_by: str = Query("updated_at"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    customer_id: Optional[int] = None,
    agency_id: Optional[int] = None,
    area: Optional[str] = None,
    offer_status: Optional[str] = None,
    pricing_status: Optional[str] = None,
):
    """
    BizQ-style list with pagination + counts.
    """

    # base selectable
    empty_int_array = sa.text("ARRAY[]::int[]")
    proj_ids_expr = func.coalesce(
        sa.cast(func.array_agg(sa.distinct(PpaProject.id)), pg.ARRAY(sa.Integer)),
        empty_int_array,
    ).label("proj_ids")

    sum_kw_expr = func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw")

    # columns we need in Python for formatting
    stmt = (
        sa.select(
            PpaBundle.id.label("bundle_id"),
            Plan.id.label("plan_id"),
            Plan.name.label("plan_name"),
            Customer.name.label("customer_name"),
            Agency.id.label("agency_id"),
            Agency.name.label("agency_name"),
            PpaBundle.area,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.quote_valid_days,
            PpaBundle.contract_start_date,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
            PpaBundle.updated_at,
            func.count(PpaSupplyPoint.id).label("sp_count"),
            sum_kw_expr,
            proj_ids_expr,
        )
        .join(Plan, Plan.id == PpaBundle.plan_id)
        .join(Customer, Customer.id == PpaBundle.customer_id)
        .outerjoin(Agency, Agency.id == PpaBundle.agency_id)
        .outerjoin(PpaSupplyPoint, PpaSupplyPoint.bundle_id == PpaBundle.id)
        .outerjoin(PpaProject, PpaProject.bundle_id == PpaBundle.id)
        .group_by(
            PpaBundle.id, Plan.id, Plan.name, Customer.name, Agency.id, Agency.name,
            PpaBundle.area, PpaBundle.requested_at, PpaBundle.request_due_date,
            PpaBundle.quote_valid_days, PpaBundle.contract_start_date,
            PpaBundle.quote_status, PpaBundle.offer_status, PpaBundle.updated_at,
        )
    )

    # filters (mirror on filtered_count)
    if customer_id is not None:
        stmt = stmt.where(PpaBundle.customer_id == customer_id)
    if agency_id is not None:
        stmt = stmt.where(PpaBundle.agency_id == agency_id)
    if area:
        stmt = stmt.where(PpaBundle.area == area)
    if pricing_status:
        stmt = stmt.where(PpaBundle.quote_status == pricing_status)
    if offer_status:
        stmt = stmt.where(PpaBundle.offer_status == offer_status)

    # ordering
    order_col_map = {
        "updated_at": PpaBundle.updated_at,
        "id": PpaBundle.id,
        "contract_start_date": PpaBundle.contract_start_date,
    }
    order_col = order_col_map.get(sort_by, PpaBundle.updated_at)
    stmt = stmt.order_by(order_col.desc() if sort_order == "desc" else order_col.asc())

    # pagination
    stmt = stmt.limit(rows).offset((page - 1) * rows)

    # counts
    base_count = sa.select(func.count()).select_from(PpaBundle)
    if customer_id is not None:
        base_count = base_count.where(PpaBundle.customer_id == customer_id)
    if agency_id is not None:
        base_count = base_count.where(PpaBundle.agency_id == agency_id)
    if area:
        base_count = base_count.where(PpaBundle.area == area)
    if pricing_status:
        base_count = base_count.where(PpaBundle.quote_status == pricing_status)
    if offer_status:
        base_count = base_count.where(PpaBundle.offer_status == offer_status)

    total_count_stmt = sa.select(func.count()).select_from(PpaBundle)
    total_count = (await session.execute(total_count_stmt)).scalar_one()
    filtered_count = (await session.execute(base_count)).scalar_one()

    rows_db = (await session.execute(stmt)).all()

    pricing_map, offer_map = _status_maps()

    data: List[PpaQuotationListItem] = []
    for r in rows_db:
        region_id, region_en, region_jp = _region_from_area(r.area)
        summary = _summary_number(r.bundle_id)
        proj_ids = list(r.proj_ids or [])
        project_count = len([pid for pid in proj_ids if pid is not None])
        contract_power_kw = float(r.sum_kw or 0.0)
        sp_count = int(r.sp_count or 0)

        # validity
        valid_label, exp_date_str = _valid_until_string(r.requested_at, r.quote_valid_days)

        # statuses
        p_id, p_en, p_jp = pricing_map.get(str(r.quote_status) if r.quote_status else "DRAFT", (1, "pending", "保留中"))
        o_id, o_en, o_jp = offer_map.get(str(r.offer_status) if r.offer_status else "NONE", (1, "pending", "保留中"))

        # last updated
        last_upd = r.updated_at
        last_upd_str = last_upd.strftime("%Y-%m-%d %H:%M") if isinstance(last_upd, datetime) else None

        data.append(
            PpaQuotationListItem(
                id=r.bundle_id,
                tender_number=summary,
                customer_name=r.customer_name,
                plan_id=int(r.plan_id),
                plan_name_en=r.plan_name,
                plan_name_jp=r.plan_name,
                sales_agent_id=int(r.agency_id) if r.agency_id is not None else None,
                sales_agent_name=r.agency_name,
                region_id=region_id,
                region_name_en=region_en,
                region_name_jp=region_jp,
                quote_request_date=r.requested_at,
                last_date_for_quotation=r.request_due_date,
                quote_valid_until=valid_label,
                contract_start_date=r.contract_start_date,
                num_of_spids=sp_count,
                peak_demand=None,
                annual_usage=None,
                pricing_status_id=p_id,
                pricing_status_en=p_en,
                pricing_status_jp=p_jp,
                offer_status_id=o_id,
                offer_status_en=o_en,
                offer_status_jp=o_jp,
                last_updated=last_upd_str,
                has_quotation_file=False,
                summary_number=summary,
                project_count=project_count,
                contract_power_kw=contract_power_kw,
                expiration_date=exp_date_str,
            )
        )

    return PpaQuotationListResponse(
        total_count=int(total_count),
        filtered_count=int(filtered_count),
        data=data,
    )


# --- DETAIL --------------------------------------------------------------

@router.get("/{bundle_id}", response_model=PpaQuotationDetailResponse)
async def get_ppa_quotation_detail(
    bundle_id: int,
    session: AsyncSession = Depends(get_session),
):
    # ---- bundle header ----
    b_stmt = (
        sa.select(
            PpaBundle.id.label("bundle_id"),
            Plan.id.label("plan_id"),
            Plan.name.label("plan_name"),
            Customer.name.label("customer_name"),
            Agency.id.label("agency_id"),
            Agency.name.label("agency_name"),
            PpaBundle.area,
            PpaBundle.requested_at,
            PpaBundle.request_due_date,
            PpaBundle.quote_valid_days,
            PpaBundle.contract_start_date,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
            PpaBundle.updated_at,
        )
        .join(Plan, Plan.id == PpaBundle.plan_id)
        .join(Customer, Customer.id == PpaBundle.customer_id)
        .outerjoin(Agency, Agency.id == PpaBundle.agency_id)
        .where(PpaBundle.id == bundle_id)
    )
    b_row = (await session.execute(b_stmt)).one_or_none()
    if not b_row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Bundle not found")

    pricing_map, offer_map = _status_maps()
    region_id, region_en, region_jp = _region_from_area(b_row.area)
    summary = _summary_number(b_row.bundle_id)
    valid_label, exp_date_str = _valid_until_string(b_row.requested_at, b_row.quote_valid_days)

    p_id, p_en, p_jp = pricing_map.get(str(b_row.quote_status) if b_row.quote_status else "DRAFT", (1, "pending", "保留中"))
    o_id, o_en, o_jp = offer_map.get(str(b_row.offer_status) if b_row.offer_status else "NONE", (1, "pending", "保留中"))

    last_upd = b_row.updated_at
    last_upd_str = last_upd.strftime("%Y-%m-%d %H:%M") if isinstance(last_upd, datetime) else None

    # ---- bundle-level SP totals (since SPs don’t link to project) ----
    sp_totals_stmt = (
        sa.select(
            func.count(PpaSupplyPoint.id).label("sp_count"),
            func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw"),
        )
        .where(PpaSupplyPoint.bundle_id == bundle_id)
    )
    sp_totals = (await session.execute(sp_totals_stmt)).one()
    total_sp = int(sp_totals.sp_count or 0)
    total_kw = float(sp_totals.sum_kw or 0.0)

    # ---- projects (no SP join) ----
    proj_stmt = (
        sa.select(
            PpaProject.id.label("project_id"),
            (func.coalesce(PpaProject.capacity_mw, 0.0) * 1000.0).label("capacity_kw"),
        )
        .where(PpaProject.bundle_id == bundle_id)
        .order_by(PpaProject.id.asc())
    )
    proj_rows = (await session.execute(proj_stmt)).all()

    projects: List[PpaProjectBrief] = []
    for pr in proj_rows:
        projects.append(
            PpaProjectBrief(
                project_id=int(pr.project_id),
                capacity_kw=float(pr.capacity_kw or 0.0),
                # placeholders until supply points carry a project link:
                supply_point_count=0,
                contract_power_kw=0.0,
            )
        )

    return PpaQuotationDetailResponse(
        id=b_row.bundle_id,
        tender_number=summary,
        customer_name=b_row.customer_name,
        plan_id=int(b_row.plan_id),
        plan_name_en=b_row.plan_name,
        plan_name_jp=b_row.plan_name,
        sales_agent_id=int(b_row.agency_id) if b_row.agency_id is not None else None,
        sales_agent_name=b_row.agency_name,
        region_id=region_id,
        region_name_en=region_en,
        region_name_jp=region_jp,
        quote_request_date=b_row.requested_at,
        last_date_for_quotation=b_row.request_due_date,
        quote_valid_until=valid_label,
        contract_start_date=b_row.contract_start_date,
        num_of_spids=total_sp,
        peak_demand=None,
        annual_usage=None,
        pricing_status_id=p_id,
        pricing_status_en=p_en,
        pricing_status_jp=p_jp,
        offer_status_id=o_id,
        offer_status_en=o_en,
        offer_status_jp=o_jp,
        last_updated=last_upd_str,
        has_quotation_file=False,
        summary_number=summary,
        project_count=len(projects),
        contract_power_kw=total_kw,
        expiration_date=exp_date_str,
        projects=projects,
        supply_points_count=total_sp,
    )
