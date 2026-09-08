from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class ListParams:
    q: str | None = None
    page: int = 1
    limit: int = 20
    sort: str | None = None
    status: str | None = None
    start_date: str | None = None
    end_date: str | None = None


def parse_date_range(start: str | None, end: str | None) -> tuple[datetime | None, datetime | None]:
    def parse_one(value: str | None, is_end: bool) -> datetime | None:
        if not value:
            return None
        v = value.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(v, fmt)
                if is_end and fmt == "%Y-%m-%d":
                    dt = dt + timedelta(days=1) - timedelta(seconds=1)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    return parse_one(start, False), parse_one(end, True)


def list_meta(page: int, limit: int, total: int) -> dict:
    return {"page": page, "limit": limit, "total": total}


def envelope(data, meta: dict | None = None) -> dict:
    return {"data": data, "meta": meta if meta is not None else {}}
