from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models import (
    Plan, Agency, Customer,
    PpaBundle, PpaProject, PpaSupplyPoint,
    VoltageLevel,  # <-- IMPORTANT
)

# -------------------- engine/session --------------------

def make_sessionmaker() -> async_sessionmaker[AsyncSession]:
    dsn = None
    try:
        from app.settings import settings  # same config the API uses
        dsn = getattr(settings, "database_url", None) or getattr(settings, "DATABASE_URL", None)
    except Exception:
        pass

    if not dsn:
        dsn = (
            os.getenv("DATABASE_URL")
            or os.getenv("DB_URL")
            or "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
        )

    print(f"🔗 Seeding into DSN: {dsn}")
    engine = create_async_engine(dsn, echo=False, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)

SessionLocal = make_sessionmaker()

# -------------------- demo data -------------------------

BUNDLE_IDS = [9001, 9002, 9003]
PLAN_IDS = [101, 102, 103]
AGENCY_IDS = [23, 24, 25]
CUSTOMER_IDS = [501, 502, 503]

PROJECTS = {
    9001: [(12001, 0.0), (12002, 0.5), (12003, 1.0)],
    9002: [(22001, 0.2), (22002, 0.8)],
    9003: [(32001, 1.5)],
}

async def seed():
    async with SessionLocal() as s:
        # Clear previous demo rows
        await s.execute(sa.delete(PpaSupplyPoint).where(PpaSupplyPoint.bundle_id.in_(BUNDLE_IDS)))
        await s.execute(sa.delete(PpaProject).where(PpaProject.bundle_id.in_(BUNDLE_IDS)))
        await s.execute(sa.delete(PpaBundle).where(PpaBundle.id.in_(BUNDLE_IDS)))
        await s.execute(sa.delete(Customer).where(Customer.id.in_(CUSTOMER_IDS)))
        await s.execute(sa.delete(Agency).where(Agency.id.in_(AGENCY_IDS)))
        await s.execute(sa.delete(Plan).where(Plan.id.in_(PLAN_IDS)))
        await s.commit()

        # Reference data
        plans = [
            Plan(id=101, name="Flat (Seasonal)"),
            Plan(id=102, name="EcoBiz Plan (LV) + PPA"),
            Plan(id=103, name="100% green market linked price plan"),
        ]
        agencies = [
            Agency(id=23, number="AG023", name="Demo Agency"),
            Agency(id=24, number="AG024", name="North Sales"),
            Agency(id=25, number="AG025", name="Kansai Partners"),
        ]
        customers = [
            Customer(id=501, name="Demo Customer", agency_id=23),
            Customer(id=502, name="ACME Foods", agency_id=24),
            Customer(id=503, name="Hikari Retail", agency_id=25),
        ]
        s.add_all(plans + agencies + customers)
        await s.flush()

        # Bundles (NOTE: voltage is required)
        base_request = date(2025, 7, 1)
        request_due  = date(2025, 7, 25)

        bundles = [
            PpaBundle(
                id=9001, customer_id=501, agency_id=23, plan_id=101,
                voltage=VoltageLevel.LOW, area="Tokyo",
                contract_start_date=date(2025, 9, 1),
                quote_valid_days=60, requested_at=base_request, request_due_date=request_due,
                prev_supplier_plan=None,
            ),
            PpaBundle(
                id=9002, customer_id=502, agency_id=24, plan_id=102,
                voltage=VoltageLevel.HIGH, area="Tohoku",
                contract_start_date=date(2025, 11, 1),
                quote_valid_days=30, requested_at=base_request + timedelta(days=10),
                request_due_date=request_due + timedelta(days=7),
                prev_supplier_plan=None,
            ),
            PpaBundle(
                id=9003, customer_id=503, agency_id=25, plan_id=103,
                voltage=VoltageLevel.EXTRA_HIGH, area="Kansai",
                contract_start_date=date(2025, 12, 1),
                quote_valid_days=60, requested_at=base_request + timedelta(days=20),
                request_due_date=request_due + timedelta(days=14),
                prev_supplier_plan=None,
            ),
        ]
        s.add_all(bundles)
        await s.flush()

        # Projects
        for bundle_id, plist in PROJECTS.items():
            for proj_id, cap in plist:
                s.add(PpaProject(
                    id=proj_id, bundle_id=bundle_id,
                    capacity_mw=cap, ppa_unit_price_yen_per_kwh=None,
                ))
        await s.flush()

        # Supply points
        sps_9001 = [
            PpaSupplyPoint(bundle_id=9001, project_id=12001, name="SP-9001-A", address="Tokyo A",
                           supply_point_number="SP-9001-A", contract_kw=500),
            PpaSupplyPoint(bundle_id=9001, project_id=12001, name="SP-9001-B", address="Tokyo B",
                           supply_point_number="SP-9001-B", contract_kw=440),
            PpaSupplyPoint(bundle_id=9001, project_id=None, name="SP-9001-C", address="Tokyo C",
                           supply_point_number="SP-9001-C", contract_kw=600),
            PpaSupplyPoint(bundle_id=9001, project_id=None, name="SP-9001-D", address="Tokyo D",
                           supply_point_number="SP-9001-D", contract_kw=450),
            PpaSupplyPoint(bundle_id=9001, project_id=None, name="SP-9001-E", address="Tokyo E",
                           supply_point_number="SP-9001-E", contract_kw=400),
            PpaSupplyPoint(bundle_id=9001, project_id=None, name="SP-9001-F", address="Tokyo F",
                           supply_point_number="SP-9001-F", contract_kw=430),
        ]
        sps_9002 = [
            PpaSupplyPoint(bundle_id=9002, project_id=22001, name="SP-9002-A", address="Tohoku A",
                           supply_point_number="SP-9002-A", contract_kw=300),
            PpaSupplyPoint(bundle_id=9002, project_id=22001, name="SP-9002-B", address="Tohoku B",
                           supply_point_number="SP-9002-B", contract_kw=250),
            PpaSupplyPoint(bundle_id=9002, project_id=22002, name="SP-9002-C", address="Tohoku C",
                           supply_point_number="SP-9002-C", contract_kw=350),
            PpaSupplyPoint(bundle_id=9002, project_id=22002, name="SP-9002-D", address="Tohoku D",
                           supply_point_number="SP-9002-D", contract_kw=150),
        ]
        sps_9003 = [
            PpaSupplyPoint(bundle_id=9003, project_id=32001, name="SP-9003-A", address="Kansai A",
                           supply_point_number="SP-9003-A", contract_kw=700),
            PpaSupplyPoint(bundle_id=9003, project_id=32001, name="SP-9003-B", address="Kansai B",
                           supply_point_number="SP-9003-B", contract_kw=500),
        ]

        s.add_all(sps_9001 + sps_9002 + sps_9003)
        await s.commit()

        total = (await s.execute(sa.select(sa.func.count()).select_from(PpaBundle))).scalar_one()
        ids = (await s.execute(sa.select(PpaBundle.id).order_by(PpaBundle.id))).scalars().all()
        print(f"✅ Seed complete. Bundles in DB: {total} -> {ids}")

if __name__ == "__main__":
    asyncio.run(seed())
