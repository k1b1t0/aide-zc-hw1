import calendar
import datetime
from typing import Optional
from django.utils import timezone

from maintenance.models import Task


def _add_months_to_date(source_date: datetime.date, months: int) -> datetime.date:
    """Add `months` to `source_date`, clipping day of month if necessary (e.g. Jan 31 -> Feb 28)."""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def calculate_next_due(task: Task, completion_date: Optional[datetime.date] = None, reference_date: Optional[datetime.date] = None) -> datetime.date:
    """Calculate the next due date for a task based on its interval type and recurrence value."""
    ref_today = reference_date or timezone.now().date()
    comp_date = completion_date or ref_today

    if task.interval_type == Task.IntervalType.ELAPSED:
        # Dynamic elapsed: adds interval_value days from actual completion date
        return comp_date + datetime.timedelta(days=task.interval_value)

    elif task.interval_type == Task.IntervalType.CALENDAR:
        # Calendar interval: task.interval_value can represent months or days.
        # If last next_due exists, advance strictly by interval from that target anchor.
        # Otherwise, anchor from completion_date.
        base_anchor = task.next_due or comp_date

        # We assume interval_value in calendar mode represents days if > 30 and not a clean month multiple,
        # or treat it as days/months. To be flexible: if interval_value <= 12, treat as months;
        # if interval_value > 12, check if divisible by 30 or treat as days.
        # More cleanly: support days offset if interval_value >= 28 and not typical month counts,
        # or check interval_value directly: let's determine days vs months.
        # In household tasks (e.g. quarterly = 3 months or 90 days).
        # Let's treat interval_value as days unless specified or support days.
        # Wait, what does the spec say?
        # "interval_value: PositiveIntegerField (representing days or months)"
        # "For CALENDAR mode: next_due advances strictly by the fixed interval cadence from the previous target date"
        # "Edge case handled: leap year dates (e.g. Feb 29) and month-end dates (e.g. Jan 31 + 1 month) do not throw ValueError"
        # This implies calendar mode can advance by months when interval_value <= 12 (or month-based) or days.
        # Let's support months when interval_value <= 12 (months: 1=monthly, 3=quarterly, 6=semi-annual, 12=yearly)
        # or when explicitly days.
        # Actually, let's treat interval_value as months if <= 12, else days.
        # Let's check both: if interval_value <= 12, we can advance by months; if > 12, advance by days.
        # Or even better: if interval_value <= 12, treat as months.
        next_date = base_anchor
        while True:
            if task.interval_value <= 12:
                next_date = _add_months_to_date(next_date, task.interval_value)
            else:
                next_date = next_date + datetime.timedelta(days=task.interval_value)

            # Ensure that if completed overdue, next_due does not remain in the past
            if next_date > comp_date and next_date >= ref_today:
                break

        return next_date

    else:
        return comp_date + datetime.timedelta(days=task.interval_value)


def get_day_countdown(next_due_date: Optional[datetime.date], reference_date: Optional[datetime.date] = None) -> Optional[int]:
    """Return remaining days until next_due_date. Positive: remaining days, 0: due today, negative: overdue."""
    if next_due_date is None:
        return None
    ref_date = reference_date or timezone.now().date()
    return (next_due_date - ref_date).days


def format_countdown_status(countdown_days: Optional[int]) -> str:
    """Format day countdown into a human readable status string."""
    if countdown_days is None:
        return "Not scheduled"
    if countdown_days > 0:
        return f"Due in {countdown_days} day{'s' if countdown_days != 1 else ''}"
    elif countdown_days == 0:
        return "Due today"
    else:
        overdue_days = abs(countdown_days)
        return f"Overdue by {overdue_days} day{'s' if overdue_days != 1 else ''}"
