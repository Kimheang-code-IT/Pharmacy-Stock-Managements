"""Dashboard endpoints — spec section 2.1.1 (API only, no UI in this phase)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import envelope, get_db_session, require_permission
from app.modules.auth.models import User
from app.modules.dashboard.schemas import DashboardOut, Envelope
from app.modules.dashboard.service import DashboardService
from datetime import date

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=Envelope[DashboardOut])
async def dashboard_summary(
    period: str = Query(default="7d", pattern="^(7d|month|custom)$"),
    start_date: date | None = Query(default=None, alias="startDate"),
    end_date: date | None = Query(default=None, alias="endDate"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("dashboard.view")),
) -> dict:
    service = DashboardService(db)
    data = await service.summary(period=period, start=start_date, end=end_date, actor=actor)
    return envelope(DashboardOut.model_validate(data))
