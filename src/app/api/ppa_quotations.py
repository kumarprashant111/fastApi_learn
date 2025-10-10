# src/app/api/ppa_quotations.py
from __future__ import annotations
from typing import Optional, List, Tuple, Dict
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects import postgresql as pg
from fastapi import APIRouter, Depends, Query

from app.db import get_session
from app.models import (
    PpaBundle, PpaProject, PpaSupplyPoint, Plan, Customer, Agency
)
from app.schemas_ppa_quotations import QuotationListItem, QuotationListResponse


router = APIRouter(prefix="/ppa_quotations", tags=["ppa_quotations"])

# --- Mappings (adjust to your enums/areas if needed) ---
_REGION_MAP: Dict[str, Tuple[int, str, str]] = {
    "HOKKAIDO": (1, "Hokkaido", "北海道"),
    "TOHOKU":   (2, "Tohoku",   "東北"),
    "KANTO":    (3, "Tokyo",    "東京"),
    "CHUBU":    (4, "Chubu",    "中部"),
    "HOKURIKU": (5, "Hokuriku", "北陸"),
    "KANSAI":   (6, "Kansai",   "関西"),
    "CHUGOKU":  (7, "Chugoku",  "中国"),
    "SHIKOKU":  (8, "Shikoku",  "四国"),
    "KYUSHU":   (9, "Kyushu",   "九州"),
}

_PRICING_STATUS_MAP: Dict[str, Tuple[int, str, str]] = {
    "DRAFT":   (1, "pending",     "保留中"),
    "PRELIM":  (2, "preliminary", "暫定"),
    "FINAL":   (3, "final",       "確定"),
}

_OFFER_STATUS_MAP: Dict[str, Tuple[int, str, str]] = {
    "NONE":       (1, "pending",   "保留中"),
    "OFFERED":    (2, "offered",   "提示済み"),
    "ACCEPTED":   (3, "accepted",  "受諾"),
    "REJECTED":   (4, "rejected",  "却下"),
    "WITHDRAWN":  (5, "withdrawn", "撤回"),
}


def _status_triplet(value: Optional[str],
                    mapping: Dict[str, Tuple[int, str, str]]) -> Tuple[int, str, str]:
    if value is None:
        return (1, "pending", "保留中")
    return mapping.get(str(value), (1, "pending", "保留中"))


def _make_tender_number(bundle_id: int) -> str:
    # Placeholder generator. Replace if you have a real tender numbering scheme.
    return f"PPA{bundle_id:08d}"


@router.get("", response_model=QuotationListResponse)
async def list_ppa_quotations(
    session: AsyncSession = Depends(get_session),

    # BizQ-like params
    page: int = Query(1, ge=1),
    rows: int = Query(20, ge=1, le=200),
    sort_by: str = Query("updated_at"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),

    # Filters
    customer_id: Optional[int] = None,
    agency_id: Optional[int] = None,
    region: Optional[str] = Query(None, description="KANTO, TOHOKU, etc."),
    pricing_status: Optional[str] = Query(None, description="DRAFT/PRELIM/FINAL"),
    offer_status: Optional[str] = Query(None, description="NONE/OFFERED/ACCEPTED/..."),
):
    """
    BizQ-style list for PPA quotations + extra columns for PPA screen:
    returns { total_count, filtered_count, data: [...] }
    """

    # ---- Shared filters
    filters = []
    if customer_id is not None:
        filters.append(PpaBundle.customer_id == customer_id)
    if agency_id is not None:
        filters.append(PpaBundle.agency_id == agency_id)
    if region:
        filters.append(PpaBundle.area == region)
    if pricing_status:
        filters.append(PpaBundle.quote_status == pricing_status)
    if offer_status:
        filters.append(PpaBundle.offer_status == offer_status)

    # ---- Counts
    total_count_stmt = sa.select(func.count(PpaBundle.id))
    total_count = int((await session.execute(total_count_stmt)).scalar() or 0)

    if filters:
        filtered_count_stmt = sa.select(func.count(PpaBundle.id)).where(*filters)
        filtered_count = int((await session.execute(filtered_count_stmt)).scalar() or 0)
    else:
        filtered_count = total_count

    # ---- Data query (includes project_count, contract_power_kw)
    empty_int_array = sa.text("ARRAY[]::int[]")
    proj_ids_expr = func.coalesce(
        sa.cast(func.array_agg(sa.distinct(PpaProject.id)), pg.ARRAY(sa.Integer)),
        empty_int_array,
    ).label("proj_ids")

    project_count_expr = func.count(sa.distinct(PpaProject.id)).label("project_count")
    sp_count_expr = func.count(PpaSupplyPoint.id).label("sp_count")
    sum_kw_expr = func.coalesce(func.sum(PpaSupplyPoint.contract_kw), 0.0).label("sum_kw")

    sort_map = {
        "updated_at": PpaBundle.updated_at,
        "quote_request_date": PpaBundle.requested_at,
        "last_date_for_quotation": PpaBundle.request_due_date,
        "contract_start_date": PpaBundle.contract_start_date,
    }
    sort_col = sort_map.get(sort_by, PpaBundle.updated_at)
    order_by_expr = sort_col.desc() if sort_order.lower() == "desc" else sort_col.asc()

    data_stmt = (
        sa.select(
            PpaBundle.id.label("bundle_id"),
            Plan.id.label("plan_id"),
            Plan.name.label("plan_name"),
            Customer.name.label("customer_name"),
            Agency.id.label("agency_id"),
            Agency.name.label("agency_name"),
            PpaBundle.area,
            PpaBundle.contract_start_date,
            PpaBundle.requested_at,           # this is the quote_request_date we’ll use
            PpaBundle.request_due_date,       # last_date_for_quotation
            PpaBundle.quote_valid_days,
            PpaBundle.quote_status,
            PpaBundle.offer_status,
            PpaBundle.updated_at,
            sp_count_expr,
            sum_kw_expr,
            proj_ids_expr,
            project_count_expr,
        )
        .join(Plan, Plan.id == PpaBundle.plan_id)
        .join(Customer, Customer.id == PpaBundle.customer_id)
        .outerjoin(Agency, Agency.id == PpaBundle.agency_id)
        .outerjoin(PpaSupplyPoint, PpaSupplyPoint.bundle_id == PpaBundle.id)
        .outerjoin(PpaProject, PpaProject.bundle_id == PpaBundle.id)
        .where(*filters)
        .group_by(
            PpaBundle.id, Plan.id, Plan.name,
            Customer.name, Agency.id, Agency.name,
            PpaBundle.area, PpaBundle.contract_start_date,
            PpaBundle.requested_at, PpaBundle.request_due_date,
            PpaBundle.quote_valid_days, PpaBundle.quote_status,
            PpaBundle.offer_status, PpaBundle.updated_at,
        )
        .order_by(order_by_expr, PpaBundle.id.desc())
        .limit(rows)
        .offset((page - 1) * rows)
    )

    rs = (await session.execute(data_stmt)).all()

    def region_triplet(area: Optional[str]) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        if not area:
            return (None, None, None)
        return _REGION_MAP.get(str(area), (None, None, None))

    items: List[QuotationListItem] = []
    for r in rs:
        rid, r_en, r_jp = region_triplet(r.area)

        ps_id, ps_en, ps_jp = _status_triplet(
            None if r.quote_status is None else str(r.quote_status), _PRICING_STATUS_MAP
        )
        os_id, os_en, os_jp = _status_triplet(
            None if r.offer_status is None else str(r.offer_status), _OFFER_STATUS_MAP
        )

        # Compute expiration from requested_at + quote_valid_days (if both exist)
        expiration_date = None
        if r.requested_at is not None and r.quote_valid_days is not None:
            try:
                expiration_date = r.requested_at + timedelta(days=int(r.quote_valid_days))
            except Exception:
                expiration_date = None

        qvu_str = None
        if expiration_date is not None and r.quote_valid_days is not None:
            qvu_str = f"{expiration_date:%Y-%m-%d} ({int(r.quote_valid_days)}日)"

        last_updated_str = r.updated_at.strftime("%Y-%m-%d %H:%M") if r.updated_at else None
        tender = _make_tender_number(int(r.bundle_id))

        items.append(
            QuotationListItem(
                # BizQ core
                id=int(r.bundle_id),
                tender_number=tender,

                customer_name=r.customer_name,

                plan_id=int(r.plan_id),
                plan_name_en=r.plan_name,
                plan_name_jp=r.plan_name,  # mirror EN until JP field exists

                sales_agent_id=int(r.agency_id) if r.agency_id is not None else None,
                sales_agent_name=r.agency_name,

                region_id=rid,
                region_name_en=r_en,
                region_name_jp=r_jp,

                quote_request_date=r.requested_at,
                last_date_for_quotation=r.request_due_date,
                quote_valid_until=qvu_str,

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

                last_updated=last_updated_str,
                has_quotation_file=False,

                # Additions for PPA screen
                summary_number=tender,  # use tender for now
                project_count=int(r.project_count or 0),
                contract_power_kw=float(r.sum_kw or 0.0),
                expiration_date=expiration_date,  # date only OK for Pydantic
            )
        )

    return QuotationListResponse(
        total_count=total_count,
        filtered_count=filtered_count,
        data=items,
    )
