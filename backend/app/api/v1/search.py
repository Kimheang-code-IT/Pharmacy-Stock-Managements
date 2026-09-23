"""Global keyword search for the SPA command palette.

Read-only and cross-module. Each result type is included only when the caller
holds the matching view permission, so a cashier never sees supplier/sales hits
they cannot open.
"""

from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import envelope, get_current_user, get_db_session
from app.core.permissions import user_has_permission
from app.modules.auth.models import User

router = APIRouter(prefix="/search", tags=["search"])

_MAX_PER_TYPE = 10


def _qty(value: object) -> str:
    return format(Decimal(value or 0).normalize(), "f")


@router.get("")
async def search(
    q: str = Query(default=""),
    limit: int = Query(default=12, ge=1, le=50),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(get_current_user),
) -> dict:
    needle = q.strip()
    if not needle:
        return envelope({"hits": [], "total": 0})
    pattern = f"%{needle}%"
    lowered = needle.lower()
    hits: list[dict] = []

    if user_has_permission(actor, "stock.view"):
        from app.modules.stock.models import Product, StockBalance

        rows = (
            await db.execute(
                select(Product.id, Product.name, Product.barcode, StockBalance.quantity)
                .outerjoin(StockBalance, StockBalance.product_id == Product.id)
                .where(Product.status == "ACTIVE")
                .where(or_(Product.name.ilike(pattern), Product.barcode.ilike(pattern)))
                .order_by(Product.name)
                .limit(_MAX_PER_TYPE)
            )
        ).all()
        for product_id, name, barcode, quantity in rows:
            hits.append({
                "id": str(product_id),
                "type": "product",
                "title": name,
                "subtitle": f"{barcode} \u00b7 Qty {_qty(quantity)}",
                "url": f"/stock/products/{product_id}",
            })

    if user_has_permission(actor, "customer.view"):
        from app.modules.customers.models import Customer

        rows = (
            await db.execute(
                select(Customer)
                .where(Customer.status == "ACTIVE")
                .where(or_(Customer.name.ilike(pattern), Customer.code.ilike(pattern), Customer.phone.ilike(pattern)))
                .order_by(Customer.name)
                .limit(_MAX_PER_TYPE)
            )
        ).scalars().all()
        for customer in rows:
            hits.append({
                "id": str(customer.id),
                "type": "customer",
                "title": customer.name,
                "subtitle": " \u00b7 ".join(value for value in (customer.code, customer.phone) if value),
                "url": f"/setup/customers/{customer.id}",
            })

    if user_has_permission(actor, "supplier.view"):
        from app.modules.suppliers.models import Supplier

        rows = (
            await db.execute(
                select(Supplier)
                .where(Supplier.status == "ACTIVE")
                .where(or_(Supplier.name.ilike(pattern), Supplier.code.ilike(pattern), Supplier.phone.ilike(pattern)))
                .order_by(Supplier.name)
                .limit(_MAX_PER_TYPE)
            )
        ).scalars().all()
        for supplier in rows:
            hits.append({
                "id": str(supplier.id),
                "type": "supplier",
                "title": supplier.name,
                "subtitle": " \u00b7 ".join(value for value in (supplier.code, supplier.phone) if value),
                "url": f"/setup/suppliers/{supplier.id}",
            })

    if user_has_permission(actor, "report.sales"):
        from app.modules.pos.models import Sale

        rows = (
            await db.execute(
                select(Sale.id, Sale.invoice_no, Sale.grand_total, Sale.currency)
                .where(Sale.invoice_no.ilike(pattern))
                .order_by(Sale.invoice_no.desc())
                .limit(_MAX_PER_TYPE)
            )
        ).all()
        for sale_id, invoice_no, grand_total, currency in rows:
            hits.append({
                "id": str(sale_id),
                "type": "sale",
                "title": invoice_no,
                "subtitle": f"{grand_total} {currency}",
                "url": f"/reports/sales?q={quote(invoice_no)}",
            })

    hits.sort(key=lambda hit: (not str(hit["title"]).lower().startswith(lowered), str(hit["title"]).lower()))
    return envelope({"hits": hits[:limit], "total": len(hits)})
