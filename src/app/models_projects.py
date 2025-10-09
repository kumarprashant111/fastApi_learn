# src/app/models_projects.py
from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    String, Integer, Float, Date, DateTime, ForeignKey, Enum as SAEnum, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base  # your existing Base

# --- enums that align with the ticket ---

class Voltage(str, Enum):
    HIGH = "HIGH"          # 高圧
    EXTRA_HIGH = "EXTRA_HIGH"  # 特別高圧
    LOW = "LOW"            # 低圧

class QuoteStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"

class OfferStatus(str, Enum):
    NONE = "NONE"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


# ============== bundle (まとめ番号) ==============

class Bundle(Base):
    """
    One row = one 'まとめ番号' (what the list shows as a single line).
    A bundle contains many capacity projects and many supply points.
    """
    __tablename__ = "bundles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # foreign keys to your existing reference tables
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    agency_id:   Mapped[int] = mapped_column(ForeignKey("agencies.id"), index=True)
    plan_id:     Mapped[int] = mapped_column(ForeignKey("plans.id"),    index=True)

    voltage: Mapped[Voltage] = mapped_column(SAEnum(Voltage), default=Voltage.HIGH)
    area:    Mapped[str]     = mapped_column(String(30), index=True)

    contract_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    quote_valid_days:    Mapped[Optional[int]]  = mapped_column(default=30)

    requested_at:       Mapped[Optional[date]] = mapped_column(Date, nullable=True)      # 見積依頼日
    request_due_date:   Mapped[Optional[date]] = mapped_column(Date, nullable=True)      # 作成要望期日

    quote_status: Mapped[QuoteStatus] = mapped_column(SAEnum(QuoteStatus), default=QuoteStatus.DRAFT)
    offer_status: Mapped[OfferStatus] = mapped_column(SAEnum(OfferStatus), default=OfferStatus.NONE)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    # relationships
    projects:      Mapped[list["CapacityProject"]] = relationship(back_populates="bundle", cascade="all, delete-orphan")
    supply_points: Mapped[list["SupplyPoint"]]     = relationship(back_populates="bundle", cascade="all, delete-orphan")


# ============== capacity projects (案件番号) ==============

class CapacityProject(Base):
    """
    One row = one '案件番号' per generation capacity scenario under a bundle.
    """
    __tablename__ = "capacity_projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("bundles.id"), index=True)

    capacity_mw: Mapped[float] = mapped_column()  # include 0.0 for PPS-only
    ppa_unit_price_yen_per_kwh: Mapped[Optional[float]] = mapped_column(nullable=True)  # tax excl.

    bundle: Mapped[Bundle] = relationship(back_populates="projects")


# ============== supply points (供給地点) ==============

class SupplyPoint(Base):
    __tablename__ = "supply_points"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("bundles.id"), index=True)

    name: Mapped[str]  = mapped_column(String(200))
    address: Mapped[Optional[str]] = mapped_column(String(300))
    supply_point_number: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    contract_kw: Mapped[Optional[float]] = mapped_column(default=0.0)

    bundle: Mapped[Bundle] = relationship(back_populates="supply_points")
