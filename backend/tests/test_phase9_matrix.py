from datetime import date, datetime, timezone

from app.training.context import derive_local_date
from app.training.service import _plan_week


def test_asia_shanghai_midnight_boundary_is_server_derived():
    before = datetime(2026, 8, 16, 15, 59, 59, tzinfo=timezone.utc)
    after = datetime(2026, 8, 16, 16, 0, 0, tzinfo=timezone.utc)
    assert derive_local_date(before, "Asia/Shanghai") == date(2026, 8, 16)
    assert derive_local_date(after, "Asia/Shanghai") == date(2026, 8, 17)


def test_asia_shanghai_sunday_to_monday_advances_plan_week():
    confirmed = datetime(2026, 8, 9, 4, 0, 0, tzinfo=timezone.utc)
    assert _plan_week(confirmed, date(2026, 8, 9), "Asia/Shanghai") == 1
    assert _plan_week(confirmed, date(2026, 8, 10), "Asia/Shanghai") == 2
