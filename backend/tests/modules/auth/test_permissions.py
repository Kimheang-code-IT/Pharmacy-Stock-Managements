from app.core.permissions import (
    PERMISSION_CATALOG,
    ASSIGNABLE_PERMISSIONS,
    SUPER_ADMIN_PERMISSION,
    build_all_permissions,
    cashier_permissions,
    effective_permissions,
    normalize_role_permissions,
    user_has_permission,
)


def test_permission_catalog_matches_spec():
    expected = {
        "dashboard": {"view", "view_profit"},
        "category": {"view", "create", "update", "delete"},
        "brand": {"view", "create", "update", "delete"},
        "uom": {"view", "create", "update", "delete"},
        "stock": {"view", "in", "adjust", "damage", "expire"},
        "product": {"create", "update", "delete"},
        "supplier": {"view", "create", "update", "delete", "debt.pay"},
        "pos": {"access", "discount", "debt_sale", "print", "sale_edit", "return", "refund"},
        "customer": {"view", "create", "update", "delete", "debt.pay"},
        "delivery": {"view", "create", "update", "confirm", "deliver", "cancel"},
        "report": {
            "sales", "purchase", "customer_debt", "supplier_debt", "finance",
            "stock_valuation", "expense",
        },
        "expense": {"view", "create", "approve", "void"},
        "user": {"view", "create", "update", "delete"},
        "role": {"view", "create", "update", "delete"},
        "sequence": {"view", "create", "update", "delete"},
        "audit": {"view"},
        "settings": {"view", "update"},
        "system": {"maintenance", "data_reset", "backup", "restore"},
    }
    assert {module: set(actions) for module, actions in PERMISSION_CATALOG.items()} == expected


def test_normalize_rejects_unknown_permissions():
    try:
        normalize_role_permissions(["not.a.permission"])
    except ValueError as exc:
        assert "not.a.permission" in str(exc)
    else:
        raise AssertionError("unknown permission must be rejected")


def test_normalize_grants_implied_view_permission():
    granted = normalize_role_permissions(["stock.in"])
    assert "stock.in" in granted
    assert "stock.view" in granted


def test_normalize_grants_view_for_dotted_debt_permission():
    granted = normalize_role_permissions(["supplier.debt.pay"])
    assert "supplier.debt.pay" in granted
    assert "supplier.view" in granted

    customer_granted = normalize_role_permissions(["customer.debt.pay"])
    assert "customer.view" in customer_granted


def test_normalize_expands_legacy_manage_permissions():
    granted = normalize_role_permissions(["user.manage", "settings.manage"])
    assert "user.view" in granted
    assert "user.create" in granted
    assert "user.update" in granted
    assert "user.delete" in granted
    assert "settings.view" in granted
    assert "settings.update" in granted
    assert "user.manage" not in granted
    assert "settings.manage" not in granted


def test_effective_permissions_and_superuser_bypass():
    class Role:
        name = "Administrator"
        permissions = []  # even with empty rows, Administrator is full access

    class User:
        role_ref = Role()

    assert effective_permissions(User()) == [SUPER_ADMIN_PERMISSION]
    assert user_has_permission(User(), "stock.in") is True
    assert user_has_permission(User(), "user.create") is True
    assert user_has_permission(User(), "role.update") is True

    class CashierRole:
        name = "Cashier"
        permissions = cashier_permissions()

    class Cashier:
        role_ref = CashierRole()

    assert user_has_permission(Cashier(), "pos.access") is True
    assert user_has_permission(Cashier(), "user.update") is False
