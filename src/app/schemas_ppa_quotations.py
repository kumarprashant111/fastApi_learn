# src/app/schemas_ppa_quotations.py
from __future__ import annotations
from datetime import date
from typing import List, Optional
from pydantic import BaseModel


# -------- List row (BizQ-compatible, plus a few additions we discussed) --------
class PpaQuotationListItem(BaseModel):
    id: int
    tender_number: str
    customer_name: str

    plan_id: int
    plan_name_en: str
    plan_name_jp: str

    sales_agent_id: Optional[int] = None
    sales_agent_name: Optional[str] = None

    region_id: Optional[int] = None
    region_name_en: Optional[str] = None
    region_name_jp: Optional[str] = None

    quote_request_date: Optional[date] = None
    last_date_for_quotation: Optional[date] = None
    # e.g. "2025-08-30 (60日)"
    quote_valid_until: str

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

    last_updated: str
    has_quotation_file: bool

    # Additions for PPA screen:
    summary_number: str
    project_count: int
    contract_power_kw: float
    expiration_date: Optional[date] = None

    class Config:
        from_attributes = True


class PpaQuotationListResponse(BaseModel):
    total_count: int
    filtered_count: int
    data: List[PpaQuotationListItem]


# -------- Detail models (header + per-project rows) --------
class PpaQuotationDetailProject(BaseModel):
    project_id: int
    capacity_mw: Optional[float] = None
    num_of_spids: int
    contract_power_kw: float

    class Config:
        from_attributes = True


class PpaQuotationDetail(BaseModel):
    # Header fields (same as list item + extras)
    id: int
    tender_number: str
    customer_name: str

    plan_id: int
    plan_name_en: str
    plan_name_jp: str

    sales_agent_id: Optional[int] = None
    sales_agent_name: Optional[str] = None

    region_id: Optional[int] = None
    region_name_en: Optional[str] = None
    region_name_jp: Optional[str] = None

    quote_request_date: Optional[date] = None
    last_date_for_quotation: Optional[date] = None
    quote_valid_until: str
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

    last_updated: str
    has_quotation_file: bool

    # Additions
    summary_number: str
    project_count: int
    contract_power_kw: float
    expiration_date: Optional[date] = None

    # Children (capacity-split projects)
    projects: List[PpaQuotationDetailProject]

    class Config:
        from_attributes = True
