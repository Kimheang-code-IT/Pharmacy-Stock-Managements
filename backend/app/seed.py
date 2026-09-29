"""Seed entrypoint (`python -m app.seed`) — tests / manual bootstrap only.

The api container does NOT run this on start: the app boots empty and the first
administrator is created on the Setup page. Kept for the test suite and for an
operator who explicitly wants the default master data.

- syncs the permission catalog and the Administrator system role
- bootstraps the initial administrator from SEED_ADMIN_* when no user exists
  (only when SEED_ADMIN_ENABLED=true; otherwise the SPA Initial Setup page
  creates the first administrator)

Local Docker convenience only; production must supply strong SEED_ADMIN_*
values (validated against the same rules as the API config).
"""

import asyncio

from app.core.config import settings


async def seed() -> None:
    from app.core.database import SessionFactory
    from app.core.security import hash_password

    # Import every model module before any ORM work so SQLAlchemy can
    # configure all mappers (relationships resolve by class name).
    import app.modules.administration.models  # noqa: F401
    import app.modules.auth.models  # noqa: F401
    import app.modules.brands.models  # noqa: F401
    import app.modules.categories.models  # noqa: F401
    import app.modules.customers.models  # noqa: F401
    import app.modules.pos.models  # noqa: F401
    import app.modules.stock.models  # noqa: F401
    import app.modules.suppliers.models  # noqa: F401
    import app.modules.uoms.models  # noqa: F401
    import app.shared.audit.models  # noqa: F401
    import app.shared.documents.models  # noqa: F401

    from app.modules.auth.models import User
    from app.modules.auth.repository import RoleRepository, UserRepository
    from app.shared.documents import ensure_default_sequences

    async with SessionFactory() as session:
        roles = RoleRepository(session)
        users = UserRepository(session)

        await roles.ensure_administrator_role()
        admin_role = await roles.get_by_name("Administrator")
        assert admin_role is not None

        if settings.seed_admin_enabled and not await users.any_user_exists():
            session.add(
                User(
                    full_name=settings.seed_admin_name,
                    email=settings.seed_admin_email.lower(),
                    password_hash=hash_password(settings.seed_admin_password),
                    telegram_chat_id=None,
                    telegram_verified=False,
                    role_id=admin_role.id,
                    status="ACTIVE",
                )
            )
            await session.flush()

        # Default document sequences (INV, STI, STA, DMG, EXP, DN, CUS, SUP, CDP, SDP).
        await ensure_default_sequences(session)

        # Default units of measure (spec section 2.1.3): PCS/BOX/CAN/BTL/KG/PACK.
        from app.modules.uoms.service import ensure_default_uoms

        await ensure_default_uoms(session)

        if not settings.is_production:
            await _seed_sample_master_data(session)

        # System walk-in customer for POS sales (spec section 2.1.6).
        from app.modules.customers.service import ensure_walk_in_customer

        await ensure_walk_in_customer(session)

        await session.commit()


async def _seed_sample_master_data(session) -> None:
    """Local-Docker convenience samples: sample brands and one draft delivery
    note when completed sales exist. Production seeds never invent demo data."""
    from sqlalchemy import select

    from app.modules.auth.models import User
    from app.modules.brands.models import Brand
    from app.modules.delivery.models import DeliveryNote, DeliveryNoteItem, DeliveryNoteSale
    from app.modules.pos.models import Sale

    for code, name in (("GEN", "Generic"), ("PREM", "Premium")):
        exists = await session.scalar(select(Brand).where(Brand.code == code))
        if exists is None:
            session.add(Brand(code=code, name=name, status="ACTIVE"))
    await session.flush()

    any_note = await session.scalar(select(DeliveryNote.id).limit(1))
    if any_note is not None:
        return
    sale = await session.scalar(
        select(Sale)
        .where(Sale.sale_status.in_(["COMPLETED", "PARTIAL_RETURN"]))
        .order_by(Sale.sale_date)
        .limit(1)
    )
    if sale is None:
        return
    admin = await session.scalar(select(User).order_by(User.created_at).limit(1))
    if admin is None:
        return
    from app.shared.documents import allocate_document_number as _allocate

    note = DeliveryNote(
        delivery_no=await _allocate(session, "DELIVERY_NOTE"),
        customer_id=sale.customer_id,
        status=DeliveryNote.STATUS_DRAFT,
        created_by=admin.id,
    )
    session.add(note)
    await session.flush()
    session.add(
        DeliveryNoteSale(
            delivery_note_id=note.id,
            sale_id=sale.id,
            invoice_no=sale.invoice_no,
        )
    )
    for item in sale.items:
        session.add(
            DeliveryNoteItem(
                delivery_note_id=note.id,
                sale_id=sale.id,
                sale_item_id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                uom_symbol=item.uom_symbol,
                qty_ordered=item.quantity,
                qty_to_deliver=item.quantity - item.returned_quantity,
                qty_delivered=0,
            )
        )


def main() -> None:
    if settings.is_production and settings.seed_admin_enabled:
        weak = (
            not settings.seed_admin_password
            or len(settings.seed_admin_password) < 12
            or settings.seed_admin_password == "123456"
        )
        if weak:
            raise RuntimeError("SEED_ADMIN_PASSWORD is too weak for production seeding")
    asyncio.run(seed())


if __name__ == "__main__":
    main()
