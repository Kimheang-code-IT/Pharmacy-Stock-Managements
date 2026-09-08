import pytest
from tests.utils import admin_headers

@pytest.mark.asyncio
async def test_debug_finance_window(client):
    headers = await admin_headers(client)
    dash = (await client.get("/api/v1/dashboard/summary?period=7d", headers=headers)).json()["data"]
    print("PERIOD", dash["period_start"], dash["period_end"])
    fin = await client.get(
        f"/api/v1/reports/finance/summary?startDate={dash['period_start']}&endDate={dash['period_end']}",
        headers=headers,
    )
    print("FIN", fin.json()["data"]["operating_expenses"], fin.request.url)
    dash2 = (await client.get("/api/v1/dashboard/summary?period=custom&startDate=%s&endDate=%s" % (dash['period_start'], dash['period_end']), headers=headers)).json()["data"]
    print("DASH custom", dash2["summary"]["total_expense"])
