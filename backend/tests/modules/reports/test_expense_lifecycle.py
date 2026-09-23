"""Expense lifecycle: DRAFT → POSTED → VOID (spec Phase 4).

Only POSTED expenses affect the Finance report / cash flow. Posted expenses are
immutable; corrections use void + replacement. Separate permissions gate
create, approve/post and void.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.utils import admin_headers, create_user_with_role, login


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


async def _expense(client, headers, **overrides):
    payload = {
        "date": _today(),
        "category": "Utilities",
        "amount": "50.00",
        "payment_method": "CASH",
    }
    payload.update(overrides)
    return await client.post("/api/v1/reports/finance/expenses", json=payload, headers=headers)


async def _finance_expense(client, headers) -> Decimal:
    data = (await client.get("/api/v1/reports/finance", headers=headers)).json()["data"]
    return Decimal(data["operating_expenses"])


@pytest.mark.asyncio
async def test_draft_expense_does_not_affect_reports_until_posted(client):
    headers = await admin_headers(client)
    before = await _finance_expense(client, headers)

    created = await _expense(client, headers, status="DRAFT")
    assert created.status_code == 201, created.text
    expense = created.json()["data"]
    assert expense["status"] == "DRAFT"

    # Draft is invisible to the Finance report.
    assert await _finance_expense(client, headers) == before
    entries = (await client.get("/api/v1/reports/finance/entries?type=EXPENSE", headers=headers)).json()["data"]
    assert all(row["id"] != expense["id"] for row in entries)

    # Post it -> now it counts.
    posted = await client.post(f"/api/v1/reports/finance/expenses/{expense['id']}/post", headers=headers)
    assert posted.status_code == 200, posted.text
    assert posted.json()["data"]["status"] == "POSTED"
    after = await _finance_expense(client, headers)
    assert after - before == Decimal("50.00")


@pytest.mark.asyncio
async def test_void_expense_removes_it_from_reports(client):
    headers = await admin_headers(client)
    created = await _expense(client, headers, amount="30.00")
    expense = created.json()["data"]
    with_expense = await _finance_expense(client, headers)

    voided = await client.post(
        f"/api/v1/reports/finance/expenses/{expense['id']}/void",
        json={"reason": "duplicate entry"},
        headers=headers,
    )
    assert voided.status_code == 200, voided.text
    assert voided.json()["data"]["status"] == "VOID"
    assert voided.json()["data"]["void_reason"] == "duplicate entry"

    assert with_expense - await _finance_expense(client, headers) == Decimal("30.00")


@pytest.mark.asyncio
async def test_posted_expense_is_immutable(client):
    headers = await admin_headers(client)
    expense = (await _expense(client, headers)).json()["data"]
    patched = await client.patch(
        f"/api/v1/reports/finance/expenses/{expense['id']}",
        json={"amount": "1.00"},
        headers=headers,
    )
    assert patched.status_code == 409, patched.text


@pytest.mark.asyncio
async def test_draft_expense_is_editable(client):
    headers = await admin_headers(client)
    expense = (await _expense(client, headers, status="DRAFT", amount="10.00")).json()["data"]
    patched = await client.patch(
        f"/api/v1/reports/finance/expenses/{expense['id']}",
        json={"amount": "12.50", "category": "Rent"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["amount"] == "12.50"
    assert patched.json()["data"]["category"] == "Rent"


@pytest.mark.asyncio
async def test_expense_lifecycle_permissions(client, db_session):
    email = f"exp-acct-{uuid.uuid4().hex[:8]}@example.com"
    await create_user_with_role(
        db_session,
        email=email,
        password="AcctUser1",
        role_name=f"Acct {uuid.uuid4().hex[:6]}",
        permissions=["report.finance", "expense.create"],
    )
    await db_session.commit()
    data = await login(client, email, "AcctUser1")
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    created = await _expense(client, headers)
    assert created.status_code == 201, created.text
    expense = created.json()["data"]

    # Without expense.approve / expense.void these are denied.
    assert (
        await client.post(f"/api/v1/reports/finance/expenses/{expense['id']}/post", headers=headers)
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/reports/finance/expenses/{expense['id']}/void",
            json={"reason": "nope"},
            headers=headers,
        )
    ).status_code == 403
