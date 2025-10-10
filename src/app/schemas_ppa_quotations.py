# src/app/schemas_ppa_quotations.py
from __future__ import annotations

from datetime import date
from typing import List, Optional
from pydantic import BaseModel


# ---------- List row (one “まとめ番号” / bundle) ----------
class PpaQuotationListItem(BaseModel):
    # BizQ-aligned fields
    id: int
    tender_number: str
    customer_name: str
    plan_id: int
    plan_name_en: str
    plan_name_jp: str
    sales_agent_id: Optional[int] = None
    sales_agent_name: Optional[str] = None

    region_id: int
    region_name_en: str
    region_name_jp: str

    quote_request_date: Optional[date] = None
    last_date_for_quotation: Optional[date] = None
    quote_valid_until: Optional[str] = None  # e.g. "2025-08-30 (60日)"

    contract_start_date: Optional[date] = None

    num_of_spids: int
    peak_demand: Optional[float] = None
    annual_usage: Optional[float] = None

    pricing_status_id: int
    pricing_status_en: str
    pricing_status_jp: str

    offer_status_id: int
    offer_status_en: str
    offer_status_jp: str

    last_updated: Optional[str] = None  # "YYYY-MM-DD HH:MM"
    has_quotation_file: bool = False

    # PPA-specific additions to satisfy requirements
    summary_number: str                 # = tender_number / まとめ番号
    project_count: int                  # 案件数（発電容量別の案件）
    contract_power_kw: float            # 契約電力（kW）
    expiration_date: Optional[str] = None  # ISO date (same date in quote_valid_until)

    class Config:
        from_attributes = True


class PpaQuotationListResponse(BaseModel):
    total_count: int
    filtered_count: int
    data: List[PpaQuotationListItem]


# ---------- Detail (bundle + child projects) ----------
class PpaProjectBrief(BaseModel):
    project_id: int
    capacity_kw: float                 # derived from capacity_mw * 1000
    supply_point_count: int
    contract_power_kw: float

    class Config:
        from_attributes = True


class PpaQuotationDetailResponse(PpaQuotationListItem):
    # hierarchy info for the diagram:
    projects: List[PpaProjectBrief]
    supply_points_count: int
