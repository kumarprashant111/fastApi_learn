# src/app/schemas_projects.py
from __future__ import annotations
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel


# -------------------------
# Existing projects list row
# -------------------------
class ProjectListRow(BaseModel):
    id: int                                  # bundle id (summary number)
    project_numbers: List[int]               # child project ids
    plan: str
    customer: str
    agency: Optional[str] = None
    area: str
    supply_point_count: int
    contracted_power_kw: float
    annual_usage_kwh: float                  # placeholder (0 for now)
    contract_start_date: Optional[date] = None
    expiration_date: Optional[date] = None   # not modeled; leave None
    last_renewed_at: Optional[datetime] = None  # not modeled; leave None
    quotation_requested_at: Optional[date] = None
    requested_preparation_date: Optional[date] = None
    quote_status: Optional[str] = None
    offer_status: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------
# BizQ-like Quotation list response
# ---------------------------------
class QuotationListItem(BaseModel):
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

    quote_request_date: Optional[str] = None         # ISO date string
    last_date_for_quotation: Optional[str] = None    # ISO date string
    quote_valid_until: Optional[str] = None          # e.g. "2025-11-02 (30日)"
    contract_start_date: Optional[str] = None        # ISO date string

    num_of_spids: int
    peak_demand: Optional[float] = None
    annual_usage: Optional[float] = None

    pricing_status_id: Optional[int] = None
    pricing_status_en: Optional[str] = None
    pricing_status_jp: Optional[str] = None

    offer_status_id: Optional[int] = None
    offer_status_en: Optional[str] = None
    offer_status_jp: Optional[str] = None

    last_updated: Optional[str] = None               # "YYYY-MM-DD HH:MM"
    has_quotation_file: bool = False


class QuotationListResponse(BaseModel):
    total_count: int
    filtered_count: int
    data: List[QuotationListItem]
