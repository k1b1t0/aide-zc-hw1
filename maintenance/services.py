import calendar
import datetime
from typing import Optional
from django.utils import timezone

from maintenance.models import Task, TaskHistory


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
        return comp_date + datetime.timedelta(days=task.interval_value)

    elif task.interval_type == Task.IntervalType.CALENDAR:
        base_anchor = task.next_due or comp_date
        next_date = base_anchor
        while True:
            if task.interval_value <= 12:
                next_date = _add_months_to_date(next_date, task.interval_value)
            else:
                next_date = next_date + datetime.timedelta(days=task.interval_value)

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


def _sanitize_table_cell(text: str) -> str:
    """Escape pipes and replace newlines so markdown tables remain intact."""
    if not text:
        return ""
    # Replace newlines with space and escape pipe
    return str(text).replace("\r\n", " ").replace("\n", " ").replace("|", "\\|").strip()


def generate_markdown_report(reference_date: Optional[datetime.date] = None) -> str:
    """
    Generate a formatted Markdown report of all tasks, their statuses, countdowns,
    and completion history.
    """
    now_utc = timezone.now()
    ref_today = reference_date or now_utc.date()
    timestamp_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# Household Maintenance Report",
        f"Generated on: {timestamp_str}",
        "",
    ]

    tasks = list(Task.objects.all().order_by("id"))

    if not tasks:
        lines.append("## Overdue Tasks")
        lines.append("_No maintenance tasks recorded._")
        lines.append("")
        lines.append("## Upcoming Tasks")
        lines.append("_No maintenance tasks recorded._")
        lines.append("")
        lines.append("## Completion History")
        lines.append("_No completion history recorded._")
        lines.append("")
        return "\n".join(lines)

    overdue_tasks = []
    upcoming_tasks = []

    for task in tasks:
        countdown = get_day_countdown(task.next_due, reference_date=ref_today)
        if countdown is not None and countdown < 0:
            overdue_tasks.append((task, abs(countdown)))
        else:
            # upcoming or unscheduled
            # sort key helper: treat None as far future
            upcoming_tasks.append((task, countdown))

    # Sort upcoming tasks by next_due ascending (None at end)
    upcoming_tasks.sort(key=lambda item: (item[0].next_due is None, item[0].next_due or datetime.date.max))

    # Overdue section
    lines.append("## Overdue Tasks")
    if overdue_tasks:
        lines.append("| Task ID | Title | Recurrence | Next Due Date | Days Overdue |")
        lines.append("| --- | --- | --- | --- | --- |")
        for task, days_overdue in overdue_tasks:
            title_clean = _sanitize_table_cell(task.title)
            recurrence = f"{task.interval_value} {task.get_interval_type_display()}"
            due_str = str(task.next_due) if task.next_due else "N/A"
            lines.append(f"| {task.id} | {title_clean} | {recurrence} | {due_str} | {days_overdue} |")
    else:
        lines.append("_No overdue tasks._")
    lines.append("")

    # Upcoming section
    lines.append("## Upcoming Tasks")
    if upcoming_tasks:
        lines.append("| Task ID | Title | Recurrence | Next Due Date | Days Remaining |")
        lines.append("| --- | --- | --- | --- | --- |")
        for task, countdown in upcoming_tasks:
            title_clean = _sanitize_table_cell(task.title)
            recurrence = f"{task.interval_value} {task.get_interval_type_display()}"
            due_str = str(task.next_due) if task.next_due else "N/A"
            rem_str = str(countdown) if countdown is not None else "N/A"
            lines.append(f"| {task.id} | {title_clean} | {recurrence} | {due_str} | {rem_str} |")
    else:
        lines.append("_No upcoming tasks._")
    lines.append("")

    # Completion History section
    lines.append("## Completion History")
    has_any_history = False
    for task in tasks:
        histories = list(task.history.all().order_by("-completed_at"))
        if histories:
            has_any_history = True
            lines.append(f"### Task #{task.id}: {_sanitize_table_cell(task.title)}")
            for h in histories:
                comp_str = h.completed_at.strftime("%Y-%m-%d %H:%M UTC")
                notes_clean = _sanitize_table_cell(h.notes) or "-"
                lines.append(f"- **{comp_str}**: {notes_clean}")
            lines.append("")

    if not has_any_history:
        lines.append("_No completion history recorded._")
        lines.append("")

    return "\n".join(lines)
