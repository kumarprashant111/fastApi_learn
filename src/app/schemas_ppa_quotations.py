from __future__ import annotations
from datetime import date
from typing import Optional, List
from pydantic import BaseModel


class QuotationListItem(BaseModel):
    # BizQ core
    id: int
    tender_number: str

    customer_name: str

    plan_id: int
    plan_name_en: str
    plan_name_jp: Optional[str] = None

    sales_agent_id: Optional[int] = None
    sales_agent_name: Optional[str] = None

    region_id: Optional[int] = None
    region_name_en: Optional[str] = None
    region_name_jp: Optional[str] = None

    quote_request_date: Optional[date] = None
    last_date_for_quotation: Optional[date] = None
    # e.g. "2025-11-02 (30日)"
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

    # "YYYY-MM-DD HH:MM"
    last_updated: Optional[str] = None
    has_quotation_file: bool

    # --- Additions/changes for PPA screen ---
    summary_number: str                     # まとめ番号（= tender_number for now）
    project_count: int                      # 案件数（distinct project ids）
    contract_power_kw: float                # 契約電力（sum of contract_kw）
    expiration_date: Optional[date] = None  # 有効期限（date only）

    class Config:
        from_attributes = True


class QuotationListResponse(BaseModel):
    total_count: int
    filtered_count: int
    data: List[QuotationListItem]
