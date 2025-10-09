from __future__ import annotations
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel
from app.models import VoltageLevel, QuoteStatus, OfferStatus

class PpaBundleListItem(BaseModel):
    id: int                                 # Summary number (まとめ番号)
    project_numbers: List[int]              # 案件番号の配列
    plan: str
    customer: str
    agency: Optional[str]
    area: str
    supply_point_count: int
    contracted_power_kw: float
    annual_usage_kwh: float                 # (0 if unknown yet)
    contract_start_date: Optional[date]
    expiration_date: Optional[date]         # derived from quote_valid_days if set
    last_renewed_at: datetime
    quotation_requested_at: Optional[date]
    requested_preparation_date: Optional[date]
    quote_status: QuoteStatus
    offer_status: OfferStatus

    class Config:
        from_attributes = True
