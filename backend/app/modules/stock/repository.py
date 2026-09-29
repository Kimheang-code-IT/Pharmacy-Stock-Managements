from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.image.service import resolve_media_url
from app.modules.stock.models import BatchStockBalance, Product, StockBalance, StockMovement


# Movement-kind grouping for the stock read model (spec section 2.1.5):
# Stock In (inbound), Stock Out (non-damage outbound), Damage (damage + expiry).
STOCK_IN_TYPES = ("STOCK_IN", "SALE_RETURN", "ADJUSTMENT_IN")
STOCK_OUT_TYPES = ("SALE", "PURCHASE_RETURN", "ADJUSTMENT_OUT")
DAMAGE_TYPES = ("DAMAGE", "EXPIRE")

# A live lot within this many days of its expiry reads as "expiring soon" on the
# product list (Expired / Expiring soon / Valid badge). Independent of the
# Telegram alert windows, which are configurable via settings.
EXPIRING_SOON_DAYS = 30


def _expiry_status(expired_qty, expiring_soon_qty, nearest_expiry) -> str | None:
    """Product-list expiry badge code, or None when the product has no dated lots."""
    if expired_qty and expired_qty > 0:
        return "expired"
    if expiring_soon_qty and expiring_soon_qty > 0:
        return "expiring"
    if nearest_expiry is not None:
        return "valid"
    return None


def _product_aggregates(product_id: uuid.UUID, grouped: dict) -> dict:
    row = grouped.get(product_id)
    if row is None:
        return {
            "stock_in_qty": Decimal("0"),
            "stock_out_qty": Decimal("0"),
            "damage_qty": Decimal("0"),
            "expiry_date": None,
            "expired_qty": Decimal("0"),
            "expiring_soon_qty": Decimal("0"),
            "expiry_status": None,
        }
    expired_qty = row.get("expired_qty") or Decimal("0")
    expiring_soon_qty = row.get("expiring_soon_qty") or Decimal("0")
    nearest_expiry = row.get("expiry_date")
    return {
        "stock_in_qty": Decimal(row["stock_in_qty"]).quantize(Decimal("0.0001")),
        "stock_out_qty": Decimal(row["stock_out_qty"]).quantize(Decimal("0.0001")),
        "damage_qty": Decimal(row["damage_qty"]).quantize(Decimal("0.0001")),
        "expiry_date": nearest_expiry,
        "expired_qty": Decimal(expired_qty).quantize(Decimal("0.0001")),
        "expiring_soon_qty": Decimal(expiring_soon_qty).quantize(Decimal("0.0001")),
        "expiry_status": _expiry_status(expired_qty, expiring_soon_qty, nearest_expiry),
    }


def product_to_out(product: Product, *, grouped: dict | None = None, pos: dict | None = None) -> dict:
    aggregates = _product_aggregates(product.id, grouped or {})
    pos = pos or {}
    pos_prices = {str(key): value for key, value in (pos.get("prices") or {}).items()}
    data = {
        "id": product.id,
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
        # Free-text brand the user typed on the product form.
        "brand": product.brand,
        "supplier_id": product.supplier_id,
        "supplier_name": product.supplier_ref.name if product.supplier_ref else None,
        "cost_price": product.cost_price,
        "selling_price": product.selling_price,
        "minimum_stock": product.minimum_stock,
        "expiry_tracking": product.expiry_tracking,
        # Batch/lot tracking switch (spec: batch management).
        "track_batch": product.track_batch,
        "fifo": product.fifo,
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
        # Batch-aware POS read model (computed in bulk by ProductService):
        # the FEFO lot's base price, its per-UOM prices, the total SELLABLE
        # stock (active + unexpired lots only) and whether a price exists.
        # `pos` is absent on create/update, where these stay null and the UI
        # falls back to the product's general selling price.
        "pos_price": pos.get("base_price"),
        "posPrice": pos.get("base_price"),
        "pos_uom_prices": pos_prices or None,
        "posUomPrices": pos_prices or None,
        "sellable_stock": pos.get("sellable_stock"),
        "sellableStock": pos.get("sellable_stock"),
        "next_batch_no": pos.get("next_batch_no"),
        "nextBatchNo": pos.get("next_batch_no"),
        "price_configured": pos.get("price_configured", True),
        "priceConfigured": pos.get("price_configured", True),
        # FEFO-ordered sellable lots for the POS cart allocation display.
        "pos_batches": pos.get("batches") or None,
        "posBatches": pos.get("batches") or None,
        # Expiry read model: nearest live expiry + expired / expiring-soon
        # remaining quantities, and the derived list status badge.
        "expiryStatus": aggregates["expiry_status"],
        "expired_qty": aggregates["expired_qty"],
        "expiredQty": aggregates["expired_qty"],
        "expiring_soon_qty": aggregates["expiring_soon_qty"],
        "expiringSoonQty": aggregates["expiring_soon_qty"],
        **aggregates,
    }
    return data


def _product_order_by(sort: str | None) -> tuple:
    """Product-list sort. `sort` is `field` or `-field` (descending).
    Unknown fields fall back to the stable default: name, id."""
    columns = {
        "name": Product.name,
        "barcode": Product.barcode,
        "status": Product.status,
        "cost_price": Product.cost_price,
        "selling_price": Product.selling_price,
        "created_at": Product.created_at,
    }
    if sort:
        column = columns.get(sort.lstrip("+-").strip())
        if column is not None:
            if sort.startswith("-"):
                return (column.desc(), Product.id.desc())
            return (column.asc(), Product.id.asc())
    return (Product.name.asc(), Product.id.asc())


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self, *, q, category_id, brand_id, status, page, limit, sort=None
    ) -> tuple[list[Product], int]:
        stmt = select(Product)
        count_stmt = select(func.count()).select_from(Product)
        if q:
            pattern = f"%{q.strip()}%"
            # Barcode-first operational search: barcode, then name. A full
            # barcode search hits the unique index.
            condition = Product.barcode.ilike(pattern) | Product.name.ilike(pattern)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
            count_stmt = count_stmt.where(Product.category_id == category_id)
        if brand_id is not None:
            stmt = stmt.where(Product.brand_id == brand_id)
            count_stmt = count_stmt.where(Product.brand_id == brand_id)
        if status:
            stmt = stmt.where(Product.status == status)
            count_stmt = count_stmt.where(Product.status == status)
        total = (await self.session.execute(count_stmt)).scalar_one()
        order_by = _product_order_by(sort)
        rows = await self.session.execute(
            stmt.order_by(*order_by).offset((page - 1) * limit).limit(limit)
        )
        return list(rows.scalars().all()), int(total)

    async def get(self, product_id: uuid.UUID) -> Product | None:
        return await self.session.get(Product, product_id)

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

    async def count_sale_items(self, product_id: uuid.UUID) -> int:
        from app.modules.pos.models import SaleItem

        result = await self.session.execute(
            select(func.count()).select_from(SaleItem).where(SaleItem.product_id == product_id)
        )
        return int(result.scalar_one())

    async def count_transaction_items(self, product_id: uuid.UUID) -> int:
        from app.modules.stock.models import StockTransactionItem

        result = await self.session.execute(
            select(func.count())
            .select_from(StockTransactionItem)
            .where(StockTransactionItem.product_id == product_id)
        )
        return int(result.scalar_one())

    async def count_purchase_return_items(self, product_id: uuid.UUID) -> int:
        from app.modules.stock.models import PurchaseReturnItem

        result = await self.session.execute(
            select(func.count())
            .select_from(PurchaseReturnItem)
            .where(PurchaseReturnItem.product_id == product_id)
        )
        return int(result.scalar_one())

    async def count_delivery_items(self, product_id: uuid.UUID) -> int:
        from app.modules.delivery.models import DeliveryNoteItem

        result = await self.session.execute(
            select(func.count())
            .select_from(DeliveryNoteItem)
            .where(DeliveryNoteItem.product_id == product_id)
        )
        return int(result.scalar_one())

    async def count_batches(self, product_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(BatchStockBalance)
            .where(BatchStockBalance.product_id == product_id)
        )
        return int(result.scalar_one())

    async def aggregate_movements(self, product_ids: list[uuid.UUID]) -> dict:
        """Per-product stock read-model aggregates.

        Returns {product_id: {stock_in_qty, stock_out_qty, damage_qty,
        expiry_date, expired_qty, expiring_soon_qty, expiry_status}}.
        stock_in/out/damage derive from immutable stock_movements; expiry_date
        is the NEAREST live-batch expiry (spec: earliest expiry_date of a lot
        with remaining_qty > 0 that has not expired; null when no such lot
        exists). expired_qty / expiring_soon_qty sum the remaining quantity of
        live lots that are already past / about to reach their expiry date.
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
        movement_rows = await self.session.execute(
            select(
                StockMovement.product_id,
                stock_in.label("stock_in_qty"),
                stock_out.label("stock_out_qty"),
                damage.label("damage_qty"),
            )
            .where(StockMovement.product_id.in_(product_ids))
            .group_by(StockMovement.product_id)
        )
        aggregates = {
            row.product_id: {
                "stock_in_qty": row.stock_in_qty,
                "stock_out_qty": row.stock_out_qty,
                "damage_qty": row.damage_qty,
                "expiry_date": None,
                "expired_qty": Decimal("0"),
                "expiring_soon_qty": Decimal("0"),
            }
            for row in movement_rows
        }
        # Nearest expiry + expired/expiring-soon quantities from the
        # authoritative per-batch ledger, not from historical movements: only
        # live lots (remaining > 0) with an expiry date participate.
        today = func.current_date()
        soon_cutoff = date.today() + timedelta(days=EXPIRING_SOON_DAYS)
        remaining = BatchStockBalance.remaining_quantity
        expiry = BatchStockBalance.expiry_date
        expiry_rows = await self.session.execute(
            select(
                BatchStockBalance.product_id,
                func.min(case((expiry >= today, expiry), else_=None)).label("nearest_expiry"),
                func.coalesce(
                    func.sum(
                        case(
                            (and_(expiry < today, remaining > 0), remaining),
                            else_=0,
                        )
                    ),
                    0,
                ).label("expired_qty"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(expiry >= today, expiry <= soon_cutoff, remaining > 0),
                                remaining,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("expiring_soon_qty"),
            )
            .where(
                BatchStockBalance.product_id.in_(product_ids),
                BatchStockBalance.expiry_date.is_not(None),
            )
            .group_by(BatchStockBalance.product_id)
        )
        for row in expiry_rows:
            entry = aggregates.setdefault(
                row.product_id,
                {
                    "stock_in_qty": Decimal("0"),
                    "stock_out_qty": Decimal("0"),
                    "damage_qty": Decimal("0"),
                    "expiry_date": None,
                    "expired_qty": Decimal("0"),
                    "expiring_soon_qty": Decimal("0"),
                },
            )
            entry["expiry_date"] = row.nearest_expiry
            entry["expired_qty"] = row.expired_qty
            entry["expiring_soon_qty"] = row.expiring_soon_qty
        return aggregates