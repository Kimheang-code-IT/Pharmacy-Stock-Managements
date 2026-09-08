from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.image.service import resolve_media_url
from app.modules.stock.models import Product, StockBalance, StockMovement


# Movement-kind grouping for the stock read model (spec section 2.1.5):
# Stock In (inbound), Stock Out (non-damage outbound), Damage (damage + expiry).
STOCK_IN_TYPES = ("STOCK_IN", "SALE_RETURN", "ADJUSTMENT_IN")
STOCK_OUT_TYPES = ("SALE", "ADJUSTMENT_OUT")
DAMAGE_TYPES = ("DAMAGE", "EXPIRE")


def _product_aggregates(product_id: uuid.UUID, grouped: dict) -> dict:
    row = grouped.get(product_id)
    if row is None:
        return {
            "stock_in_qty": Decimal("0"),
            "stock_out_qty": Decimal("0"),
            "damage_qty": Decimal("0"),
            "expiry_date": None,
        }
    return {
        "stock_in_qty": Decimal(row["stock_in_qty"]).quantize(Decimal("0.0001")),
        "stock_out_qty": Decimal(row["stock_out_qty"]).quantize(Decimal("0.0001")),
        "damage_qty": Decimal(row["damage_qty"]).quantize(Decimal("0.0001")),
        "expiry_date": row.get("expiry_date"),
    }


def product_to_out(product: Product, *, grouped: dict | None = None) -> dict:
    aggregates = _product_aggregates(product.id, grouped or {})
    data = {
        "id": product.id,
        "sku": product.sku,
        "barcode": product.barcode,
        "name": product.name,
        "category_id": product.category_id,
        "category_name": product.category_ref.name if product.category_ref else None,
        "uom_id": product.uom_id,
        "uom_code": product.uom_ref.code if product.uom_ref else None,
        "uom_name": product.uom_ref.name if product.uom_ref else None,
        "uom_symbol": product.uom_ref.symbol if product.uom_ref else None,
        "brand_id": product.brand_id,
        "brand_name": product.brand_ref.name if product.brand_ref else None,
        "cost_price": product.cost_price,
        "selling_price": product.selling_price,
        "minimum_stock": product.minimum_stock,
        "expiry_tracking": product.expiry_tracking,
        "image_object_key": product.image_object_key,
        "image_url": resolve_media_url(product.image_object_key),
        "status": product.status,
        "note": product.note,
        # Convert-UOM rows (spec 4.2); snake_case + the camelCase key the UI reads.
        "uom_conversions": product.uom_conversions or [],
        "uomConversions": product.uom_conversions or [],
        "quantity": product.balance.quantity if product.balance else Decimal("0"),
        "average_cost": product.balance.average_cost if product.balance else Decimal("0.00"),
        "created_at": product.created_at,
        **aggregates,
    }
    return data


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, q, category_id, status, page, limit) -> tuple[list[Product], int]:
        stmt = select(Product)
        count_stmt = select(func.count()).select_from(Product)
        if q:
            pattern = f"%{q.strip()}%"
            condition = Product.name.ilike(pattern) | Product.sku.ilike(pattern)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
            count_stmt = count_stmt.where(Product.category_id == category_id)
        if status:
            stmt = stmt.where(Product.status == status)
            count_stmt = count_stmt.where(Product.status == status)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(Product.name).offset((page - 1) * limit).limit(limit)
        )
        return list(rows.scalars().all()), int(total)

    async def get(self, product_id: uuid.UUID) -> Product | None:
        return await self.session.get(Product, product_id)

    async def get_by_sku(self, sku: str) -> Product | None:
        result = await self.session.execute(select(Product).where(Product.sku == sku))
        return result.scalar_one_or_none()

    async def get_by_barcode(self, barcode: str) -> Product | None:
        result = await self.session.execute(select(Product).where(Product.barcode == barcode))
        return result.scalar_one_or_none()

    async def ensure_balance(self, product_id: uuid.UUID) -> StockBalance:
        result = await self.session.execute(
            select(StockBalance).where(StockBalance.product_id == product_id)
        )
        balance = result.scalar_one_or_none()
        if balance is None:
            balance = StockBalance(product_id=product_id, quantity=Decimal("0"), average_cost=Decimal("0.00"))
            self.session.add(balance)
            await self.session.flush()
        return balance

    async def count_movements(self, product_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(StockMovement).where(StockMovement.product_id == product_id)
        )
        return int(result.scalar_one())

    async def aggregate_movements(self, product_ids: list[uuid.UUID]) -> dict:
        """Per-product movement aggregates for the stock read model.

        Returns {product_id: {stock_in_qty, stock_out_qty, damage_qty, expiry_date}}
        derived from immutable stock_movements — never from the materialized balance.
        expiry_date is the soonest non-null lot expiry on record for the product.
        """
        if not product_ids:
            return {}
        stock_in = func.coalesce(
            func.sum(
                case(
                    (StockMovement.movement_type.in_(STOCK_IN_TYPES), StockMovement.quantity_delta),
                    else_=0,
                )
            ),
            0,
        )
        stock_out = func.coalesce(
            func.sum(
                case(
                    (StockMovement.movement_type.in_(STOCK_OUT_TYPES), -StockMovement.quantity_delta),
                    else_=0,
                )
            ),
            0,
        )
        damage = func.coalesce(
            func.sum(
                case(
                    (StockMovement.movement_type.in_(DAMAGE_TYPES), -StockMovement.quantity_delta),
                    else_=0,
                )
            ),
            0,
        )
        nearest_expiry = func.min(StockMovement.expiry_date)
        stmt = (
            select(
                StockMovement.product_id,
                stock_in.label("stock_in_qty"),
                stock_out.label("stock_out_qty"),
                damage.label("damage_qty"),
                nearest_expiry.label("expiry_date"),
            )
            .where(StockMovement.product_id.in_(product_ids))
            .group_by(StockMovement.product_id)
        )
        rows = await self.session.execute(stmt)
        return {
            row.product_id: {
                "stock_in_qty": row.stock_in_qty,
                "stock_out_qty": row.stock_out_qty,
                "damage_qty": row.damage_qty,
                "expiry_date": row.expiry_date,
            }
            for row in rows
        }