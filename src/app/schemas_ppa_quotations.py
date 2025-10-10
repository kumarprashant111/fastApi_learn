# src/app/schemas_ppa_quotations.py
from __future__ import annotations

from datetime import date
from typing import List, Optional
from pydantic import BaseModel


# ---------- List (row) ----------
class PpaQuotationListItem(BaseModel):
    # BizQ-like fields
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
    quote_valid_until: Optional[str] = None  # e.g. "2025-11-02 (30日)"
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
    has_quotation_file: bool

    # PPA-specific additions required by your screen spec
    summary_number: str                 # = tender_number for display
    project_count: int                  # 案件数
    contract_power_kw: float            # 契約電力 (= sum of SP.contract_kw for bundle)
    expiration_date: Optional[date] = None  # 有効期限 (date only)

    class Config:
        from_attributes = True


class PpaQuotationListResponse(BaseModel):
    total_count: int
    filtered_count: int
    data: List[PpaQuotationListItem]


# ---------- Detail (project rows) ----------
class PpaQuotationProject(BaseModel):
    project_id: int
    capacity_mw: float
    # Per-project SP totals are unknown in current schema (no project_id on SPs)
    num_of_spids: Optional[int] = None
    contract_power_kw: Optional[float] = None

    class Config:
        from_attributes = True


# ---------- Detail (header + projects) ----------
class PpaQuotationDetail(BaseModel):
    # Same header fields as list (plus projects)
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
    quote_valid_until: Optional[str] = None
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
    last_updated: Optional[str] = None
    has_quotation_file: bool

    # PPA screen additions
    summary_number: str
    project_count: int
    contract_power_kw: float
    expiration_date: Optional[date] = None

    # Projects under the summary/bundle
    projects: List[PpaQuotationProject]

    class Config:
        from_attributes = True
