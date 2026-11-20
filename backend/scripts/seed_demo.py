"""Seed a COMPLETE demo dataset for manual/demo testing (local Docker only).

Goes through the real backend services, so every side effect a real user would
get is consistent: auto-issued 6-digit barcodes, batch lots + expiry, price
versions, document numbers (INV/PIN/CDP/...), customer & supplier debts,
payments and the stock ledger.

What it creates (skipped when a previous demo seed is detected):
  - categories / brands / suppliers / customers
  - 11 products (some batch + expiry tracked, some with BOX/CAN pricing rows)
  - 4 stock-in purchases (one partly paid, one unpaid -> supplier debts)
  - 5 POS sales: walk-in cash, bank-QR with delivery, partial cash (customer
    debt), an unpaid KHR wholesale invoice, and a cash sale + debt payment
  - one damage operation and one delivery note

Usage — inside the api container (recommended):
    docker compose -f infrastructure/docker-compose.yml exec api python scripts/seed_demo.py

Run locally without DATABASE_URL set: the connection is derived from
infrastructure/.env (Postgres on localhost:55432).

Login after seeding: admin@gmail.com / 123456 (or your SEED_ADMIN_* values
from infrastructure/.env when one already exists).

Refuses to run with ENVIRONMENT=production. To reset first:
    python scripts/clear_data.py --yes   (also wipes existing admin!)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# Backend root (the parent of scripts/) must own sys.path: running this file by
# path otherwise resolves `app` from the script directory / site-packages, and
# a stale installed copy of the package then shadows the real one.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_ENV = REPO_ROOT / "infrastructure" / ".env"

DEMO_MARKER_CATEGORY_CODE = "DEMO"

# --------------------------------------------------------------------- data

CATEGORIES = [
    {"code": DEMO_MARKER_CATEGORY_CODE, "name": "Pharmacy", "description": "Demo category"},
    {"code": "DEMO-DRK", "name": "Drinks & Beverages", "description": "Demo category"},
    {"code": "DEMO-SNK", "name": "Snacks", "description": "Demo category"},
    {"code": "DEMO-HSH", "name": "Household", "description": "Demo category"},
]

BRANDS = [
    {"code": "DEMO-A", "name": "Demo Pharma"},
    {"code": "DEMO-B", "name": "Demo Foods"},
]

SUPPLIERS = [
    {"code": "DEMO-S1", "name": "Pharma Distribution", "company_name": "Pharma Distribution Co., Ltd",
     "phone": "011111111", "address": "St 110, Phnom Penh", "contact_person": "Mr. Panha"},
    {"code": "DEMO-S2", "name": "Beverage Wholesale", "company_name": "Beverage Wholesale HH",
     "phone": "012222222", "address": "St 271, Phnom Penh", "contact_person": "Ms. Sopheak"},
    {"code": "DEMO-S3", "name": "Household Import", "company_name": "Clean Home Import",
     "phone": "012333333", "address": "Mao Tse Tong, Phnom Penh", "contact_person": "Mr. Vibol"},
]

CUSTOMERS = [
    {"code": "DEMO-C1", "name": "Sokha Chan", "phone": "017111111", "address": "Boeung Salang, Phnom Penh"},
    {"code": "DEMO-C2", "name": "Dara Kim", "phone": "017222222", "address": "Toul Kork, Phnom Penh"},
    {"code": "DEMO-C3", "name": "Sreymom Lim", "phone": "017333333", "address": "Chbar Ampov, Phnom Penh"},
    {"code": "DEMO-C4", "name": "Vuthy Mini Mart", "phone": "017444444", "address": "Prek Pnov, Phnom Penh"},
]

# name, category code, brand code, cost, sale, minimum stock, batch/expiry
# tracking, optional pricing rows ({"uom": "BOX", "factor": 20, "sale": 22.00})
PRODUCTS = [
    {"name": "Paracetamol 500mg", "category": DEMO_MARKER_CATEGORY_CODE, "brand": "DEMO-A",
     "cost": "0.55", "sale": "1.00", "minimum_stock": "50", "batch": True, "uom_rows": [
        {"uom": "BOX", "factor": 20, "sale": "18.00"}]},
    {"name": "Amoxicillin 250mg", "category": DEMO_MARKER_CATEGORY_CODE, "brand": "DEMO-A",
     "cost": "1.10", "sale": "2.00", "minimum_stock": "30", "batch": True},
    {"name": "Vitamin C 1000mg", "category": DEMO_MARKER_CATEGORY_CODE, "brand": "DEMO-A",
     "cost": "1.60", "sale": "2.50", "minimum_stock": "20", "batch": True, "uom_rows": [
        {"uom": "BOX", "factor": 10, "sale": "23.00"}]},
    {"name": "Ibuprofen 400mg", "category": DEMO_MARKER_CATEGORY_CODE, "brand": "DEMO-A",
     "cost": "0.90", "sale": "1.50", "minimum_stock": "25"},
    {"name": "Drinking Water 500ml", "category": "DEMO-DRK", "brand": "DEMO-B",
     "cost": "0.20", "sale": "0.40", "minimum_stock": "100", "uom_rows": [
        {"uom": "BOX", "factor": 24, "sale": "8.50"}]},
    {"name": "Cola Can 330ml", "category": "DEMO-DRK", "brand": "DEMO-B",
     "cost": "0.35", "sale": "0.70", "minimum_stock": "80", "uom_rows": [
        {"uom": "CAN", "factor": 24, "sale": "15.00"}]},
    {"name": "Orange Juice 1L", "category": "DEMO-DRK", "brand": "DEMO-B",
     "cost": "1.20", "sale": "2.20", "minimum_stock": "30"},
    {"name": "Potato Chips 90g", "category": "DEMO-SNK", "brand": "DEMO-B",
     "cost": "0.60", "sale": "1.10", "minimum_stock": "40"},
    {"name": "Instant Noodles", "category": "DEMO-SNK", "brand": "DEMO-B",
     "cost": "0.30", "sale": "0.55", "minimum_stock": "100", "uom_rows": [
        {"uom": "BOX", "factor": 30, "sale": "15.00"}]},
    {"name": "Dish Soap 750ml", "category": "DEMO-HSH",
     "cost": "1.40", "sale": "2.60", "minimum_stock": "20"},
    {"name": "Laundry Powder 1kg", "category": "DEMO-HSH",
     "cost": "2.30", "sale": "4.00", "minimum_stock": "15", "uom_rows": [
        {"uom": "PACK", "factor": 6, "sale": "22.00"}]},
]


def _env_file_value(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def resolve_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    user = os.environ.get("POSTGRES_USER") or _env_file_value(INFRA_ENV, "POSTGRES_USER") or "stock_pos"
    password = os.environ.get("POSTGRES_PASSWORD") or _env_file_value(INFRA_ENV, "POSTGRES_PASSWORD") or "stock_pos"
    database = os.environ.get("POSTGRES_DB") or _env_file_value(INFRA_ENV, "POSTGRES_DB") or "stock_pos"
    return f"postgresql+asyncpg://{user}:{password}@localhost:55432/{database}"


def _import_models() -> None:
    """Import every model module before ORM work (mapper configuration)."""
    import app.modules.administration.models  # noqa: F401
    import app.modules.auth.models  # noqa: F401
    import app.modules.brands.models  # noqa: F401
    import app.modules.categories.models  # noqa: F401
    import app.modules.customers.models  # noqa: F401
    import app.modules.delivery.models  # noqa: F401
    import app.modules.pos.models  # noqa: F401
    import app.modules.stock.models  # noqa: F401
    import app.modules.suppliers.models  # noqa: F401
    import app.modules.telegram.models  # noqa: F401
    import app.modules.uoms.models  # noqa: F401
    import app.shared.audit.models  # noqa: F401
    import app.shared.documents.models  # noqa: F401


async def _ensure_admin(session, role_id) -> object:
    """Demo login guarantee: create admin@gmail.com/123456 when no user exists
    (app.seed only creates one when SEED_ADMIN_ENABLED=true)."""
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.modules.auth.models import User

    user = (await session.execute(select(User).order_by(User.created_at).limit(1))).scalar_one_or_none()
    if user is not None:
        print(f"Admin login already exists: {user.email}")
        return user
    user = User(
        full_name="Demo Administrator",
        email="admin@gmail.com",
        password_hash=hash_password("123456"),
        role_id=role_id,
        status="ACTIVE",
    )
    session.add(user)
    await session.commit()
    print("Created demo administrator: admin@gmail.com / 123456")
    return user


async def _first_uom_map(session) -> dict[str, object]:
    from sqlalchemy import select

    from app.modules.uoms.models import UOM

    rows = (await session.execute(select(UOM))).scalars().all()
    return {row.code: row for row in rows}


async def run(args: argparse.Namespace) -> int:
    from app.core.config import settings

    if settings.is_production and not args.confirm_production:
        print("Refusing to seed demo data with ENVIRONMENT=production.")
        print("Demo data never belongs in real production. If this stack is a")
        print("local-only production-mode environment for demo/testing, pass")
        print("--confirm-production to proceed deliberately.")
        return 2

    from app.core.database import SessionFactory

    _import_models()

    # 1. Base bootstrap: permission catalog + Administrator role, document
    #    sequences, default UOMs, walk-in customer (idempotent).
    from app.seed import seed as base_seed

    await base_seed()

    async with SessionFactory() as session:
        from app.modules.auth.repository import RoleRepository

        admin_role = await RoleRepository(session).get_by_name("Administrator")
        assert admin_role is not None
        actor = await _ensure_admin(session, admin_role.id)

        # 2. Skip when the demo dataset already exists (marker category).
        from sqlalchemy import select

        from app.modules.categories.models import Category

        marker = (await session.execute(
            select(Category).where(Category.code == DEMO_MARKER_CATEGORY_CODE)
        )).scalar_one_or_none()
        if marker is not None:
            print("Demo data already present — nothing to do.")
            print("To reseed a fresh database: python scripts/clear_data.py --yes, then run this again.")
            return 0

        await _seed_demo(session, actor)

    print("\nDemo dataset complete. Sign in with admin@gmail.com / 123456 "
          "(or your SEED_ADMIN_* credentials).")
    return 0


async def _seed_demo(session, actor) -> None:
    from app.modules.brands.schemas import BrandCreate
    from app.modules.brands.service import BrandService
    from app.modules.categories.schemas import CategoryCreate
    from app.modules.categories.service import CategoryService
    from app.modules.customers.schemas import CustomerCreate
    from app.modules.customers.service import CustomerService
    from app.modules.delivery.schemas import DeliveryNoteFromSaleCreate
    from app.modules.delivery.service import DeliveryNoteService
    from app.modules.pos.schemas import (
        DebtPaymentRequest,
        SaleCreateRequest,
        SaleItemRequest,
    )
    from app.modules.pos.service import POSService
    from app.modules.stock.schemas import (
        ProductCreate,
        StockDamageRequest,
        StockInItem,
        StockInRequest,
    )
    from app.modules.stock.service import ProductService, StockOperationService
    from app.modules.suppliers.schemas import SupplierCreate
    from app.modules.suppliers.service import SupplierService

    today = date.today()
    uoms = await _first_uom_map(session)

    categories: dict[str, object] = {}
    for row in CATEGORIES:
        category = await CategoryService(session).create(CategoryCreate(**row))
        categories[category.code] = category

    brands: dict[str, object] = {}
    for row in BRANDS:
        brand = await BrandService(session).create(BrandCreate(**row))
        brands[brand.code] = brand

    suppliers: dict[str, object] = {}
    for row in SUPPLIERS:
        supplier = await SupplierService(session).create(SupplierCreate(**row))
        suppliers[supplier.code] = supplier

    customers: dict[str, object] = {}
    for row in CUSTOMERS:
        customer = await CustomerService(session).create(CustomerCreate(**row))
        customers[customer.code] = customer

    # ------------------------------------------------------------- products
    products: dict[str, object] = {}
    product_service = ProductService(session)
    for row in PRODUCTS:
        conversions = None
        if row.get("uom_rows"):
            conversions = [
                {
                    "uom_id": str(uoms[pricing["uom"]].id),
                    "factor_to_base": str(pricing["factor"]),
                    "sale_price": str(pricing["sale"]),
                }
                for pricing in row["uom_rows"]
            ]
        product = await product_service.create(ProductCreate(
            name=row["name"],
            category_id=categories[row["category"]].id,
            uom_id=uoms["PCS"].id,
            brand_id=brands[row["brand"]].id if row.get("brand") else None,
            cost_price=Decimal(row["cost"]),
            selling_price=Decimal(row["sale"]),
            minimum_stock=Decimal(row["minimum_stock"]),
            expiry_tracking=bool(row.get("batch")),
            track_batch=bool(row.get("batch")),
            uom_conversions=conversions,
        ))
        products[row["name"]] = product
    print(f"Created {len(products)} products (barcodes auto-issued).")

    # ------------------------------------------------------------ stock-in
    stock_service = StockOperationService(session)

    def item(name: str, qty: str, cost: str, *, batch: str | None = None, expiry: date | None = None):
        # ProductService.create returns the serialized product dict.
        return StockInItem(
            product_id=products[name]["id"], quantity=Decimal(qty), unit_cost=Decimal(cost),
            batch_no=batch, expiry_date=expiry,
        )

    # Purchase 1 — pharma, long-dated lots, half paid -> supplier debt.
    purchase1 = await stock_service.stock_in(StockInRequest(
        supplier_id=suppliers["DEMO-S1"].id,
        paid_amount=Decimal("50.00"),
        reference_no="DEMO-PO-001",
        note="Demo purchase — long-dated lots (half paid)",
        items=[
            item("Paracetamol 500mg", "200", "0.55", batch="B24001", expiry=today + timedelta(days=720)),
            item("Amoxicillin 250mg", "100", "1.10", batch="B24002", expiry=today + timedelta(days=540)),
            item("Vitamin C 1000mg", "120", "1.60", batch="B24003", expiry=today + timedelta(days=400)),
            item("Ibuprofen 400mg", "80", "0.90"),
        ],
    ), actor=actor)

    # Purchase 2 — pharma, a lot expiring soon (expiry-alert demo), unpaid.
    purchase2 = await stock_service.stock_in(StockInRequest(
        supplier_id=suppliers["DEMO-S1"].id,
        paid_amount=Decimal("0"),
        reference_no="DEMO-PO-002",
        note="Demo purchase — near-expiry lot (unpaid)",
        items=[
            item("Paracetamol 500mg", "100", "0.58", batch="B24004", expiry=today + timedelta(days=25)),
            item("Amoxicillin 250mg", "50", "1.12", batch="B24005", expiry=today + timedelta(days=40)),
        ],
    ), actor=actor)

    # Purchase 3 — beverages + snacks, fully paid.
    await stock_service.stock_in(StockInRequest(
        supplier_id=suppliers["DEMO-S2"].id,
        paid_amount=Decimal("95.00"),
        reference_no="DEMO-PO-003",
        note="Demo purchase — fully paid",
        items=[
            item("Drinking Water 500ml", "480", "0.20"),
            item("Cola Can 330ml", "240", "0.35"),
            item("Orange Juice 1L", "60", "1.20"),
            item("Potato Chips 90g", "120", "0.60"),
            item("Instant Noodles", "300", "0.30"),
        ],
    ), actor=actor)

    # Purchase 4 — household, unpaid -> visible supplier debt.
    await stock_service.stock_in(StockInRequest(
        supplier_id=suppliers["DEMO-S3"].id,
        paid_amount=Decimal("0"),
        reference_no="DEMO-PO-004",
        note="Demo purchase — on credit",
        items=[
            item("Dish Soap 750ml", "60", "1.40"),
            item("Laundry Powder 1kg", "36", "2.30"),
        ],
    ), actor=actor)
    print("Created 4 stock-in purchases (supplier debts included).")

    # ---------------------------------------------------------------- sales
    def sale_item(name: str, qty: str, **kwargs) -> SaleItemRequest:
        return SaleItemRequest(product_id=products[name]["id"], quantity=Decimal(qty), **kwargs)

    pos = POSService(session)

    # 1. Walk-in cash sale, fully paid.
    await pos.complete_sale(SaleCreateRequest(
        payment_method="CASH",
        amount_received=Decimal("3.60"),
        note="Demo walk-in sale",
        items=[sale_item("Paracetamol 500mg", "2"), sale_item("Drinking Water 500ml", "4")],
    ), actor=actor)

    # 2. Sokha — bank QR, fully paid, with delivery fee.
    sale2 = await pos.complete_sale(SaleCreateRequest(
        customer_id=customers["DEMO-C1"].id,
        payment_method="BANK_QR",
        amount_received=Decimal("9.70"),
        delivery_price=Decimal("2.00"),
        note="Demo sale with delivery",
        items=[sale_item("Orange Juice 1L", "2"), sale_item("Potato Chips 90g", "3")],
    ), actor=actor)

    # 3. Dara — cash deposit short of the total -> customer debt.
    await pos.complete_sale(SaleCreateRequest(
        customer_id=customers["DEMO-C2"].id,
        payment_method="CUSTOMER_DEBT",
        amount_received=Decimal("5.00"),
        due_date=today + timedelta(days=14),
        note="Demo partial payment (debt remains)",
        items=[sale_item("Vitamin C 1000mg", "4"), sale_item("Ibuprofen 400mg", "3")],
    ), actor=actor)

    # 4. Vuthy — KHR wholesale invoice, unpaid (KHR customer debt).
    await pos.complete_sale(SaleCreateRequest(
        customer_id=customers["DEMO-C4"].id,
        payment_method="CUSTOMER_DEBT",
        amount_received=Decimal("0"),
        currency="KHR",
        exchange_rate=Decimal("4100"),
        note="Demo KHR wholesale sale on credit",
        items=[sale_item("Instant Noodles", "2"), sale_item("Drinking Water 500ml", "10")],
    ), actor=actor)

    # 5. Sreymom — cash with delivery fee; also settles part of Dara's debt.
    await pos.complete_sale(SaleCreateRequest(
        customer_id=customers["DEMO-C3"].id,
        payment_method="CASH",
        amount_received=Decimal("7.90"),
        delivery_price=Decimal("1.50"),
        note="Demo cash sale",
        items=[sale_item("Vitamin C 1000mg", "2"), sale_item("Cola Can 330ml", "2")],
    ), actor=actor)

    print("Created 5 POS sales (cash, bank QR, partial cash, KHR credit).")

    # A delivery note from sale 2 (draft, ready for the Delivery Notes page).
    await DeliveryNoteService(session).create_from_sale(
        sale2.id,
        DeliveryNoteFromSaleCreate(
            driver_name="Sok Vanna",
            delivery_phone="017111111",
            delivery_location="Boeung Salang, Phnom Penh",
            note="Demo delivery note",
        ),
        actor=actor,
    )
    print("Created 1 delivery note.")

    # Settle part of Dara's debt (CDP payment shows in the debt report).
    debts = await CustomerService(session).list_debts(customers["DEMO-C2"].id)
    if debts:
        debt = debts[0][0]
        await CustomerService(session).pay_debt(
            customers["DEMO-C2"].id, debt.id,
            DebtPaymentRequest(amount=Decimal("3.00"), payment_method="CASH",
                               reference_no="DEMO-RC-001", note="Demo debt payment"),
            actor=actor,
        )
        print("Created 1 customer debt payment.")

    # A damage operation (shows in stock movements).
    await stock_service.damage(StockDamageRequest(
        reference_no="DEMO-DMG-001",
        note="Demo damage",
        items=[{
            "product_id": str(products["Dish Soap 750ml"]["id"]),
            "quantity": "2",
            "reason": "Bottle broken in store",
        }],
    ), actor=actor)
    print("Created 1 damage movement.")

    # Demo tip: purchase 2 has a lot expiring in ~25 days (ALERT 2 window).
    print(f"Done. Purchases: {[purchase1.document_no, purchase2.document_no]} (among others).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a complete demo dataset.")
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="allow demo data in an ENVIRONMENT=production stack (local-only demo/testing environments)",
    )
    args = parser.parse_args()
    database_url = resolve_database_url()
    os.environ.setdefault("DATABASE_URL", database_url)
    try:
        return asyncio.run(run(args))
    except ModuleNotFoundError as exc:
        print(f"Missing dependency: {exc}. Run this inside the api container.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
