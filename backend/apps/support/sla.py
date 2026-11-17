import zoneinfo
from datetime import datetime, time, timedelta
from typing import Tuple
from django.conf import settings
from django.utils import timezone
from apps.support.models import TicketPriorityChoices


def get_operational_timezone():
    tz_name = getattr(settings, 'SUPPORT_SLA_TIMEZONE', 'UTC')
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return zoneinfo.ZoneInfo('UTC')


def get_configured_holidays() -> set:
    """
    Returns a normalized set of holiday identifiers (strings in 'YYYY-MM-DD' format and date objects)
    from settings.SUPPORT_PUBLIC_HOLIDAYS.
    Supports list, set, tuple, or callable to allow dynamic external calendars.
    """
    raw = getattr(settings, 'SUPPORT_PUBLIC_HOLIDAYS', [])
    if callable(raw):
        raw = raw()
    holidays = set()
    for item in raw:
        if isinstance(item, datetime):
            holidays.add(item.date().isoformat())
            holidays.add(item.date())
        elif hasattr(item, 'isoformat'):  # datetime.date
            holidays.add(item.isoformat())
            holidays.add(item)
        elif isinstance(item, str) and item.strip():
            clean = item.strip()
            holidays.add(clean)
            try:
                holidays.add(datetime.strptime(clean, "%Y-%m-%d").date())
            except ValueError:
                pass
    return holidays


def is_business_day(dt: datetime, operational_tz=None) -> bool:
    """
    Monday=0, ..., Sunday=6. Business days are Mon-Fri (0-4),
    strictly excluding configured public/statutory holidays.
    Evaluated in the configured SUPPORT_SLA_TIMEZONE.
    """
    if operational_tz is None:
        operational_tz = get_operational_timezone()
    local_dt = dt.astimezone(operational_tz) if dt.tzinfo else dt
    if local_dt.weekday() >= 5:
        return False

    holidays = get_configured_holidays()
    date_str = local_dt.strftime('%Y-%m-%d')
    if date_str in holidays or local_dt.date() in holidays:
        return False

    return True


def calculate_business_seconds_between(
    start_dt: datetime,
    end_dt: datetime,
    priority: str = None,
) -> float:
    """
    Computes elapsed business seconds between start_dt and end_dt.
    For CRITICAL priority: returns 24/7 calendar seconds.
    For HIGH, MEDIUM, LOW priorities: respects business hours (Mon-Fri 08:00-18:00),
    weekends, and configured public/statutory holidays in SUPPORT_SLA_TIMEZONE.
    """
    if end_dt <= start_dt:
        return 0.0

    if priority == TicketPriorityChoices.CRITICAL:
        return max(0.0, (end_dt - start_dt).total_seconds())

    op_tz = get_operational_timezone()
    start_local = start_dt.astimezone(op_tz)
    end_local = end_dt.astimezone(op_tz)

    work_start_hour = 8
    work_end_hour = 18

    current_date = start_local.date()
    end_date = end_local.date()
    total_seconds = 0.0

    while current_date <= end_date:
        day_sample = datetime(current_date.year, current_date.month, current_date.day, 12, 0, tzinfo=op_tz)
        if is_business_day(day_sample, operational_tz=op_tz):
            day_work_start = datetime(current_date.year, current_date.month, current_date.day, work_start_hour, 0, tzinfo=op_tz)
            day_work_end = datetime(current_date.year, current_date.month, current_date.day, work_end_hour, 0, tzinfo=op_tz)

            window_start = max(day_work_start, start_local)
            window_end = min(day_work_end, end_local)

            if window_end > window_start:
                total_seconds += (window_end - window_start).total_seconds()

        current_date += timedelta(days=1)

    return total_seconds


def add_business_hours(start_dt: datetime, business_hours: float) -> datetime:
    """
    Calculates future deadline considering business hours:
    Monday to Friday, 08:00 to 18:00 (10 operational hours/day).
    Weekends are excluded. Input and output are timezone-aware.
    """
    op_tz = get_operational_timezone()
    current = start_dt.astimezone(op_tz)

    work_start_hour = 8
    work_end_hour = 18
    hours_per_day = work_end_hour - work_start_hour  # 10 hours

    # 1. Roll forward if outside working hours or on weekend
    while True:
        if not is_business_day(current):
            # Advance to next day 08:00
            current = (current + timedelta(days=1)).replace(hour=work_start_hour, minute=0, second=0, microsecond=0)
            continue
        if current.hour < work_start_hour:
            current = current.replace(hour=work_start_hour, minute=0, second=0, microsecond=0)
            break
        elif current.hour >= work_end_hour:
            # Advance to next day 08:00
            current = (current + timedelta(days=1)).replace(hour=work_start_hour, minute=0, second=0, microsecond=0)
            continue
        else:
            break

    remaining_hours = business_hours

    while remaining_hours > 0:
        # Available hours today until 18:00
        end_of_today = current.replace(hour=work_end_hour, minute=0, second=0, microsecond=0)
        available_today = (end_of_today - current).total_seconds() / 3600.0

        if remaining_hours <= available_today:
            current = current + timedelta(hours=remaining_hours)
            remaining_hours = 0
            break
        else:
            remaining_hours -= available_today
            # Advance to next business day 08:00
            current = (current + timedelta(days=1)).replace(hour=work_start_hour, minute=0, second=0, microsecond=0)
            while not is_business_day(current):
                current = (current + timedelta(days=1)).replace(hour=work_start_hour, minute=0, second=0, microsecond=0)

    return current.astimezone(zoneinfo.ZoneInfo('UTC'))


def calculate_sla_deadlines(priority: str, start_dt: datetime = None) -> Tuple[datetime, datetime]:
    """
    Returns (first_response_due_at, resolution_due_at) based on priority:
    - CRITICAL: 1h response, 6h resolution (24/7 calendar clock)
    - HIGH: 4h response, 24h resolution (business hours Mon-Fri 08:00-18:00)
    - MEDIUM: 12h response, 48h resolution (business hours Mon-Fri 08:00-18:00)
    - LOW: 24h response, 96h resolution (business hours Mon-Fri 08:00-18:00)
    """
    if start_dt is None:
        start_dt = timezone.now()

    if priority == TicketPriorityChoices.CRITICAL:
        # 24/7 calendar hours
        first_resp_due = start_dt + timedelta(hours=1)
        res_due = start_dt + timedelta(hours=6)
    elif priority == TicketPriorityChoices.HIGH:
        first_resp_due = add_business_hours(start_dt, 4.0)
        res_due = add_business_hours(start_dt, 24.0)
    elif priority == TicketPriorityChoices.MEDIUM:
        first_resp_due = add_business_hours(start_dt, 12.0)
        res_due = add_business_hours(start_dt, 48.0)
    else:  # LOW
        first_resp_due = add_business_hours(start_dt, 24.0)
        res_due = add_business_hours(start_dt, 96.0)

    return first_resp_due, res_due


def is_within_reopen_window(ticket, now: datetime = None) -> bool:
    """Verifies whether a resolved ticket can be reopened (default 72 hours)."""
    if now is None:
        now = timezone.now()
    if not ticket.resolved_at:
        return True
    window_hours = getattr(settings, 'SUPPORT_REOPEN_WINDOW_HOURS', 72)
    return (now - ticket.resolved_at) <= timedelta(hours=window_hours)

