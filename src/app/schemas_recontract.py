from __future__ import annotations
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from app.models import QuoteEffectiveDays  # ✅ import the SAME enum used by the ORM


class SupplyPointIn(BaseModel):
    supply_point_number: str = Field(min_length=1, max_length=64)


class PlantIn(BaseModel):
    capacity_mw: float = Field(ge=0.0)
    ppa_unit_price_yen_per_kwh: Optional[float] = Field(default=None, ge=0.0)

    @field_validator("capacity_mw")
    @classmethod
    def one_decimal_step(cls, v: float) -> float:
        return round(v, 1)


class RecontractEstimateIn(BaseModel):
    plan_id: int
    customer_id: int
    desired_quote_date: date
    quote_effective_days: QuoteEffectiveDays  # ✅ exact ORM enum
    remarks: Optional[str] = Field(default=None, max_length=500)
    supply_points: List[SupplyPointIn] = Field(min_length=1, max_length=20)
    plants: List[PlantIn] = Field(default_factory=list, max_length=3)

    @field_validator("desired_quote_date")
    @classmethod
    def within_one_month(cls, v: date) -> date:
        from datetime import date as _date, timedelta as _timedelta
        today = _date.today()
        if v < today or v > (today + _timedelta(days=31)):
            raise ValueError("desired_quote_date must be between today and +31 days")
        return v


class SupplyPointOut(SupplyPointIn):
    id: int
    model_config = {"from_attributes": True}


class PlantOut(BaseModel):
    id: int
    capacity_mw: float
    ppa_unit_price_yen_per_kwh: Optional[float]
    model_config = {"from_attributes": True}


class RecontractEstimateOut(BaseModel):
    id: int
    plan_id: int
    customer_id: int
    desired_quote_date: date
    # Pydantic will serialize Enum[int] as its .value (30/60) when field is int:
    quote_effective_days: int
    remarks: Optional[str] = None
    supply_points: List[SupplyPointOut]
    plants: List[PlantOut]

    model_config = {"from_attributes": True}
