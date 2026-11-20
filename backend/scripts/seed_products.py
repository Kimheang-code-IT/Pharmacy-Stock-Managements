"""Seed 100 demo products (with sellable stock) for local/manual testing.

Created through the real backend services, so side effects match a real user:
auto-issued 6-digit barcodes, price versions and the stock ledger.

What it creates (skips names that already exist, so it is re-runnable):
  - one "Bulk Demo" category (code DEMO-BULK)
  - 100 products (default; --count N) with realistic pharmacy/retail names
  - 1 stock-in purchase giving every product 200 units, so they can be sold
    from the POS (handy for a 100-line multi-page invoice print test)

Usage — inside the api container (recommended):
    docker compose -f infrastructure/docker-compose.yml exec api python scripts/seed_products.py

Run locally without DATABASE_URL set: the connection is derived from
infrastructure/.env (Postgres on localhost:55432).

Refuses to run with ENVIRONMENT=production (pass --confirm-production to
proceed deliberately on a local-only production-mode stack).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
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

CATEGORY_CODE = "DEMO-BULK"
CATEGORY_NAME = "Bulk Demo"

STOCK_QTY = "200"

# ------------------------------------------------------------------ names

# 100 realistic pharmacy / grocery product names.
PRODUCT_NAMES = [
    "Paracetamol 500mg", "Amoxicillin 250mg", "Ibuprofen 400mg", "Vitamin C 1000mg",
    "Cetirizine 10mg", "Loratadine 10mg", "Metformin 850mg", "Amlodipine 5mg",
    "Omeprazole 20mg", "Ranitidine 150mg", "Ciprofloxacin 500mg", "Azithromycin 500mg",
    "Cephalexin 500mg", "Dexamethasone 0.5mg", "Prednisolone 5mg", "Chlorpheniramine 4mg",
    "Salbutamol Inhaler", "ORS Sachet", "Zinc Sulphate 20mg", "Folic Acid 5mg",
    "Ferrous Sulphate 200mg", "Calcium Carbonate 500mg", "Vitamin B Complex", "Vitamin D3 1000IU",
    "Multivitamin Syrup", "Cough Syrup 100ml", "Paracetamol Syrup 60ml", "Antacid Suspension 200ml",
    "Herbal Cough Drops", "Throat Lozenges", "Ginger Candy", "Honey Lemon Tea",
    "Betadine Gargle 60ml", "Saline Nasal Spray", "Eye Drops 10ml", "Ear Drops 10ml",
    "Hydrocortisone Cream 15g", "Antifungal Cream 15g", "Acne Gel 10g", "Calamine Lotion 60ml",
    "Bandage Roll", "Gauze Pad Pack", "Medical Tape", "Cotton Wool 100g",
    "Alcohol Swabs 100pcs", "Syringe 5ml", "Digital Thermometer", "Blood Pressure Monitor",
    "Blood Glucose Test Strips", "Face Mask 50pcs", "Surgical Gloves", "Hand Sanitizer 500ml",
    "Disinfectant Spray 500ml", "Alcohol 70% 500ml", "Hydrogen Peroxide 100ml", "Baby Powder 100g",
    "Baby Wipes 80pcs", "Baby Shampoo 200ml", "Diapers M 4pcs", "Infant Formula 400g",
    "Drinking Water 500ml", "Drinking Water 1.5L", "Cola Can 330ml", "Orange Juice 1L",
    "Apple Juice 1L", "Energy Drink 250ml", "Iced Tea 500ml", "Instant Coffee Stick",
    "Milk 1L", "Soy Milk 250ml", "Yogurt Drink 180ml", "Green Tea Bottle 500ml",
    "Instant Noodles", "Potato Chips 90g", "Biscuit Pack", "Chocolate Bar 50g",
    "Candy Jar 200g", "Peanuts 150g", "Canned Sardines 155g", "Canned Tuna 180g",
    "Instant Soup Cup", "White Rice 1kg", "Cooking Oil 1L", "Fish Sauce 500ml",
    "Soy Sauce 500ml", "Salt 500g", "Sugar 1kg", "Monosodium 250g",
    "Dish Soap 750ml", "Laundry Powder 1kg", "Fabric Softener 1L", "Floor Cleaner 1L",
    "Toilet Cleaner 500ml", "Glass Cleaner 500ml", "Trash Bag M 10pcs", "Paper Towel Roll",
    "Toothpaste 100g", "Toothbrush", "Shampoo 200ml", "Body Soap 90g",
    "Detergent Bar 200g", "Mosquito Coil 10pcs", "Rat Glue Trap", "Insect Spray 300ml",
]

# Small deterministic price spread so the printed amounts look varied.
DEFAULT_COST = "0.50"
DEFAULT_SALE = "1.00"


def _price(name: str) -> tuple[str, str]:
    index = PRODUCT_NAMES.index(name) + 1
    cost = Decimal(DEFAULT_COST) + Decimal(index % 7) * Decimal("0.05")
    sale = Decimal(DEFAULT_SALE) + Decimal(index % 5) * Decimal("0.10")
    return (str(cost), str(sale))


# ------------------------------------------------------------------ helpers

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


async def run(args: argparse.Namespace) -> int:
    from sqlalchemy import select

    from app.core.config import settings

    if settings.is_production and not args.confirm_production:
        print("Refusing to seed products with ENVIRONMENT=production.")
        print("Demo data never belongs in real production. If this stack is a")
        print("local-only production-mode environment for demo/testing, pass")
        print("--confirm-production to proceed deliberately.")
        return 2

    from app.core.database import SessionFactory

    _import_models()

    # Base bootstrap: permission catalog, roles, sequences, default UOMs,
    # walk-in customer (idempotent).
    from app.seed import seed as base_seed

    await base_seed()

    async with SessionFactory() as session:
        from app.modules.auth.models import User
        from app.modules.categories.models import Category
        from app.modules.categories.schemas import CategoryCreate
        from app.modules.categories.service import CategoryService
        from app.modules.stock.models import Product
        from app.modules.stock.schemas import ProductCreate, StockInItem, StockInRequest
        from app.modules.stock.service import ProductService, StockOperationService
        from app.modules.uoms.models import UOM

        actor = (await session.execute(select(User).order_by(User.created_at).limit(1))).scalar_one_or_none()
        if actor is None:
            print("No user exists yet — finish the SPA Setup page once, or run")
            print("scripts/seed_demo.py first, then run this again.")
            return 2

        # ------------------------------------------------------- category
        category = (await session.execute(
            select(Category).where(Category.code == CATEGORY_CODE)
        )).scalar_one_or_none()
        if category is None:
            category = await CategoryService(session).create(CategoryCreate(
                code=CATEGORY_CODE, name=CATEGORY_NAME, description="Bulk demo products",
            ))
            print(f"Created category {CATEGORY_CODE} ({CATEGORY_NAME}).")
        else:
            print(f"Category {CATEGORY_CODE} already exists.")

        uom_pcs = (await session.execute(select(UOM).where(UOM.code == "PCS"))).scalars().first()
        if uom_pcs is None:
            print("No PCS UOM found — the base seed should have created it. Aborting.")
            return 2

        names = PRODUCT_NAMES[:max(1, min(args.count, len(PRODUCT_NAMES)))]

        # Skip names that already exist (re-runnable without duplicates).
        existing_names = set((await session.execute(
            select(Product.name).where(Product.name.in_(names))
        )).scalars().all())

        # ------------------------------------------------------- products
        product_service = ProductService(session)
        created = 0
        skipped = 0
        for name in names:
            if name in existing_names:
                skipped += 1
                continue
            cost, sale = _price(name)
            await product_service.create(ProductCreate(
                name=name,
                category_id=category.id,
                uom_id=uom_pcs.id,
                cost_price=Decimal(cost),
                selling_price=Decimal(sale),
                minimum_stock=Decimal("10"),
            ))
            created += 1
        print(f"Created {created} products (barcodes auto-issued); skipped {skipped} existing.")

        # ------------------------------------------------------- stock-in
        # Idempotent: the purchase reference marks the bulk stock-in as done.
        from app.modules.stock.models import StockTransaction

        already_stocked = (await session.execute(
            select(StockTransaction.id).where(StockTransaction.reference_no == "DEMO-BULK-001")
        )).scalar_one_or_none()
        if already_stocked is not None:
            print("Purchase DEMO-BULK-001 already exists — stock-in skipped.")
        else:
            # Every product of the bulk category gets stock (covers products
            # created by a previous interrupted run too).
            bulk_products = (await session.execute(
                select(Product).where(Product.category_id == category.id).order_by(Product.name)
            )).scalars().all()
            if bulk_products:
                items = [
                    StockInItem(
                        product_id=product.id,
                        quantity=Decimal(STOCK_QTY),
                        unit_cost=product.cost_price,
                    )
                    for product in bulk_products
                ]
                total = sum((item.quantity * item.unit_cost for item in items), Decimal("0"))
                stock_service = StockOperationService(session)
                await stock_service.stock_in(StockInRequest(
                    reference_no="DEMO-BULK-001",
                    note="Bulk demo products — 200 units each",
                    # No supplier: the purchase must be fully paid.
                    paid_amount=total,
                    items=items,
                ), actor=actor)
                print(f"Stocked {len(bulk_products)} products × {STOCK_QTY} units (purchase DEMO-BULK-001, paid ${total}).")

        print("\nDone. Add many lines to a POS cart and print the invoice to see")
        print("the multi-page layout (full header on page 1, continued pages after).")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed bulk demo products (default 100) with stock.")
    parser.add_argument("--count", type=int, default=100, help="how many products to create (max 100)")
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
