# src/app/models.py
from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Float, Date, DateTime, ForeignKey, Enum as SAEnum,
    Boolean, UniqueConstraint, text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ----- Reference / master tables -----

class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class Agency(Base):
    __tablename__ = "agencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    agency_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agencies.id"))
    agency: Mapped[Optional[Agency]] = relationship(lazy="selectin")


class ContractStatus(str, Enum):
    UNDER_CONTRACT = "UNDER_CONTRACT"
    RECONTRACT_ESTIMATE = "RECONTRACT_ESTIMATE"
    RECONTRACTED = "RECONTRACTED"


class AncillaryType(str, Enum):
    STANDBY_POWER = "STANDBY_POWER"
    STANDBY_LINE = "STANDBY_LINE"
    PRIVATE_POWER_SUPPLY = "PRIVATE_POWER_SUPPLY"
    NON_FOSSIL_CERT = "NON_FOSSIL_CERT"
    RENEWABLE_LEVY_REDUCTION = "RENEWABLE_LEVY_REDUCTION"
    ENECLOUD_DISCOUNT = "ENECLOUD_DISCOUNT"


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    supply_point_number: Mapped[str] = mapped_column(String(64), index=True)
    start_date: Mapped[date]
    end_date: Mapped[date]
    negotiated_power_kw: Mapped[Optional[float]] = mapped_column()
    status: Mapped[ContractStatus] = mapped_column(SAEnum(ContractStatus), default=ContractStatus.UNDER_CONTRACT)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("now()")  # ✅ server default
    )

    customer: Mapped[Customer] = relationship(lazy="selectin")
    plan: Mapped[Plan] = relationship(lazy="selectin")
    ancillary_contracts: Mapped[List["AncillaryContract"]] = relationship(
        back_populates="contract", cascade="all,delete-orphan", lazy="selectin"
    )

    __table_args__ = (UniqueConstraint("supply_point_number", "end_date", name="uq_contract_spn_end"),)


class AncillaryContract(Base):
    __tablename__ = "ancillary_contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    type: Mapped[AncillaryType] = mapped_column(SAEnum(AncillaryType))
    unit_price: Mapped[Optional[float]] = mapped_column()

    contract: Mapped[Contract] = relationship(back_populates="ancillary_contracts", lazy="selectin")


# ----- Re-contract estimate -----

class QuoteEffectiveDays(int, Enum):
    DAYS_30 = 30
    DAYS_60 = 60


class RecontractEstimate(Base):
    """
    Header record for a re-contract estimate request.
    One header can expand to multiple 'capacity scenarios' projects (0 + up to 3).
    """
    __tablename__ = "recontract_estimates"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    desired_quote_date: Mapped[date]
    quote_effective_days: Mapped[QuoteEffectiveDays] = mapped_column(SAEnum(QuoteEffectiveDays))
    remarks: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("now()")  # ✅ server default to fix your error
    )

    customer: Mapped[Customer] = relationship(lazy="selectin")
    plan: Mapped[Plan] = relationship(lazy="selectin")
    supply_points: Mapped[List["RecontractSupplyPoint"]] = relationship(
        back_populates="estimate", cascade="all,delete-orphan", lazy="selectin"
    )
    plants: Mapped[List["RecontractPlant"]] = relationship(
        back_populates="estimate", cascade="all,delete-orphan", lazy="selectin"
    )


class RecontractSupplyPoint(Base):
    __tablename__ = "recontract_supply_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("recontract_estimates.id"), index=True)
    supply_point_number: Mapped[str] = mapped_column(String(64))
    estimate: Mapped[RecontractEstimate] = relationship(back_populates="supply_points", lazy="selectin")


class RecontractPlant(Base):
    """
    Up to 3 capacity scenarios + default 0 capacity.
    """
    __tablename__ = "recontract_plants"
    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("recontract_estimates.id"), index=True)
    capacity_mw: Mapped[float]
    ppa_unit_price_yen_per_kwh: Mapped[Optional[float]]

    estimate: Mapped[RecontractEstimate] = relationship(back_populates="plants", lazy="selectin")
