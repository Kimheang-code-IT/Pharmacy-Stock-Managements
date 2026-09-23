from __future__ import annotations

from collections.abc import Iterable

SUPER_ADMIN_ROLE = "Administrator"
SUPER_ADMIN_PERMISSION = "ALL_PAGES"

# Stock & POS permission catalog (spec section 2.1.8).
PERMISSION_CATALOG: dict[str, tuple[str, ...]] = {
    "dashboard": ("view", "view_profit"),
    "category": ("view", "create", "update", "delete"),
    "uom": ("view", "create", "update", "delete"),
    "brand": ("view", "create", "update", "delete"),
    "stock": ("view", "in", "adjust", "damage", "expire"),
    "product": ("create", "update", "delete"),
    "supplier": ("view", "create", "update", "delete", "debt.pay"),
    "pos": ("access", "discount", "debt_sale", "print", "sale_edit", "return", "refund"),
    "customer": ("view", "create", "update", "delete", "debt.pay"),
    "delivery": ("view", "create", "update", "confirm", "deliver", "cancel"),
    "report": (
        "sales",
        "purchase",
        "customer_debt",
        "supplier_debt",
        "finance",
        "stock_valuation",
        "expense",
    ),
    # Operating expenses have a full lifecycle (draft → posted → void).
    "expense": ("view", "create", "approve", "void"),
    "user": ("view", "create", "update", "delete"),
    "role": ("view", "create", "update", "delete"),
    "sequence": ("view", "create", "update", "delete"),
    "audit": ("view",),
    "settings": ("view", "update"),
    "system": ("maintenance", "data_reset", "backup", "restore"),
}

# Legacy `*.manage` codes expand to CRUD so older role rows keep working.
_LEGACY_MANAGE_EXPANSION: dict[str, tuple[str, ...]] = {
    "user.manage": ("user.view", "user.create", "user.update", "user.delete"),
    "role.manage": ("role.view", "role.create", "role.update", "role.delete"),
    "sequence.manage": ("sequence.view", "sequence.create", "sequence.update", "sequence.delete"),
    "settings.manage": ("settings.view", "settings.update"),
}

SERVICE_PERMISSIONS = frozenset({"telegram.reset.send"})
ASSIGNABLE_PERMISSIONS = frozenset(
    f"{module}.{action}"
    for module, actions in PERMISSION_CATALOG.items()
    for action in actions
)


def permission_catalog() -> list[dict[str, object]]:
    return [
        {
            "module": module,
            "actions": list(actions),
            "permissions": [f"{module}.{action}" for action in actions],
        }
        for module, actions in PERMISSION_CATALOG.items()
    ]


def build_all_permissions() -> list[str]:
    codes = [key for group in permission_catalog() for key in group["permissions"]] + sorted(SERVICE_PERMISSIONS)
    codes.append(SUPER_ADMIN_PERMISSION)
    return codes


def normalize_role_permissions(values: Iterable[str] | None, *, allow_wildcard: bool = False) -> list[str]:
    expanded: list[str] = []
    for value in values or []:
        code = str(value).strip()
        if not code:
            continue
        if code in _LEGACY_MANAGE_EXPANSION:
            expanded.extend(_LEGACY_MANAGE_EXPANSION[code])
        else:
            expanded.append(code)
    normalized = list(dict.fromkeys(expanded))
    allowed = set(ASSIGNABLE_PERMISSIONS)
    if allow_wildcard:
        allowed.add(SUPER_ADMIN_PERMISSION)
    unknown = sorted(set(normalized) - allowed)
    if unknown:
        raise ValueError(f"Unknown permissions: {', '.join(unknown)}")
    granted = set(normalized)
    for permission in normalized:
        if permission.count(".") < 1:
            continue
        # Dotted actions (e.g. supplier.debt.pay) belong to the first segment's
        # module, so granting them also grants supplier.view / customer.view.
        module = permission.split(".", 1)[0]
        action = permission.rsplit(".", 1)[-1]
        view_permission = f"{module}.view"
        if action != "view" and view_permission in ASSIGNABLE_PERMISSIONS:
            granted.add(view_permission)
    ordered = [permission for permission in build_all_permissions() if permission in granted]
    if SUPER_ADMIN_PERMISSION in granted and SUPER_ADMIN_PERMISSION not in ordered:
        ordered.append(SUPER_ADMIN_PERMISSION)
    return ordered


def cashier_permissions() -> list[str]:
    return [
        "dashboard.view",
        "stock.view",
        "pos.access",
        "pos.print",
        "customer.view",
        "customer.create",
        "report.sales",
    ]


def effective_permissions(user: object) -> list[str]:
    """Resolve access exclusively from the authoritative related role.

    The system Administrator role always has full access (`ALL_PAGES`), even if
    the stored role_permissions rows are stale after a catalog change.
    """
    role = getattr(user, "role_ref", None)
    if role is None:
        return []
    # A disabled role grants nothing, even to the system Administrator role
    # (which the app also refuses to disable).
    if getattr(role, "status", "ACTIVE") != "ACTIVE":
        return []
    if getattr(role, "name", None) == SUPER_ADMIN_ROLE:
        return [SUPER_ADMIN_PERMISSION]
    values = list(getattr(role, "permissions", None) or [])
    if SUPER_ADMIN_PERMISSION in values:
        return [SUPER_ADMIN_PERMISSION]
    return [value for value in values if value in ASSIGNABLE_PERMISSIONS]


def user_has_permission(user: object, required: str) -> bool:
    values = effective_permissions(user)
    return SUPER_ADMIN_PERMISSION in values or required in values
