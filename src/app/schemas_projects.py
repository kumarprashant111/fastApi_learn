from __future__ import annotations
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field

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
    quote_status: str
    offer_status: str

    class Config:
        from_attributes = True
