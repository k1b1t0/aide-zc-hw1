import datetime
import functools
import logging
import re
from typing import Callable, List
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from maintenance.models import Task, TaskHistory
from maintenance.services import (
    calculate_next_due,
    get_day_countdown,
    format_countdown_status,
)

logger = logging.getLogger(__name__)


def authorized_only(func: Callable) -> Callable:
    """Decorator to ensure only configured authorized user IDs can execute bot commands."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        authorized_ids = getattr(settings, "TELEGRAM_AUTHORIZED_USER_IDS", [])
        if authorized_ids and (not user or user.id not in authorized_ids):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ Access Denied: You are not authorized to use this maintenance bot."
                )
            return
        return await func(update, context, *args, **kwargs)

    return wrapper


async def _reply_chunked(update: Update, lines: List[str], max_len: int = 4000) -> None:
    """Send lines grouped into messages without exceeding Telegram's character limits."""
    if not update.effective_message:
        return

    current_chunk = []
    current_length = 0

    for line in lines:
        line_len = len(line) + 1
        if current_length + line_len > max_len and current_chunk:
            await update.effective_message.reply_text("\n".join(current_chunk))
            current_chunk = [line]
            current_length = line_len
        else:
            current_chunk.append(line)
            current_length += line_len

    if current_chunk:
        await update.effective_message.reply_text("\n".join(current_chunk))


@authorized_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /start command."""
    welcome_message = (
        "👋 Welcome to the Household Maintenance Tracker Bot!\n\n"
        "I help you track and stay ahead of recurring maintenance chores.\n\n"
        "Use /help to view all available commands."
    )
    if update.effective_message:
        await update.effective_message.reply_text(welcome_message)


@authorized_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /help command."""
    help_message = (
        "🛠 *Available Commands:*\n\n"
        "• `/start` - Welcome message and introduction\n"
        "• `/help` - Show this list of commands\n"
        "• `/list` - List all maintenance tasks sorted by due date\n"
        "• `/due` - Show overdue tasks and tasks due in the next 7 days\n"
        "• `/add <title> | <interval> <days|months> | <calendar|elapsed>` - Register a new task\n"
        "• `/done <id> [notes]` - Mark a task completed today and reschedule\n"
        "• `/history <id>` - View completion history for a task\n"
        "• `/export` - Download the complete Markdown maintenance report\n"
    )
    if update.effective_message:
        await update.effective_message.reply_text(help_message, parse_mode="Markdown")


@authorized_only
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /list command: list all tasks sorted by due date."""
    tasks = await sync_to_async(list)(
        Task.objects.all().order_by("next_due", "id")
    )

    if not tasks:
        if update.effective_message:
            await update.effective_message.reply_text(
                "No maintenance tasks found. Use /add to create one."
            )
        return

    today = timezone.now().date()
    lines = ["📋 *All Maintenance Tasks:*", ""]

    for task in tasks:
        countdown = get_day_countdown(task.next_due, reference_date=today)
        status = format_countdown_status(countdown)
        due_str = f" ({task.next_due})" if task.next_due else ""
        interval_desc = f"Every {task.interval_value} {task.get_interval_type_display().lower()}"
        lines.append(f"• [{task.id}] *{task.title}* - {interval_desc} - {status}{due_str}")

    await _reply_chunked(update, lines)


@authorized_only
async def due_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /due command: list overdue tasks and tasks due in the next 7 days."""
    today = timezone.now().date()
    threshold = today + datetime.timedelta(days=7)

    tasks = await sync_to_async(list)(
        Task.objects.filter(next_due__isnull=False, next_due__lte=threshold).order_by("next_due", "id")
    )

    if not tasks:
        if update.effective_message:
            await update.effective_message.reply_text(
                "All caught up! No tasks due in the next 7 days."
            )
        return

    lines = ["⚡ *Tasks Due or Overdue:*", ""]

    for task in tasks:
        countdown = get_day_countdown(task.next_due, reference_date=today)
        if countdown is not None and countdown < 0:
            lines.append(f"⚠️ *OVERDUE by {abs(countdown)} day{'s' if abs(countdown) != 1 else ''}*: [{task.id}] {task.title} (due {task.next_due})")
        elif countdown == 0:
            lines.append(f"⏳ *Due today*: [{task.id}] {task.title}")
        else:
            lines.append(f"⏳ *Due in {countdown} day{'s' if countdown != 1 else ''}*: [{task.id}] {task.title} (due {task.next_due})")

    await _reply_chunked(update, lines)


def _sync_create_task(title: str, interval_val: int, interval_type: str) -> Task:
    task = Task(
        title=title,
        interval_value=interval_val,
        interval_type=interval_type,
    )
    initial_due = calculate_next_due(task, completion_date=timezone.now().date())
    task.next_due = initial_due
    task.save()
    return task


@authorized_only
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /add command: /add <title> | <interval_value> <days|months> | <calendar|elapsed>"""
    usage_error = (
        "❌ *Invalid format.*\n\n"
        "*Usage:*\n"
        "`/add <title> | <interval_value> <days|months> | <calendar|elapsed>`\n\n"
        "*Example:*\n"
        "`/add Clean AC Filters | 30 days | elapsed`\n"
        "`/add Inspect Roof | 12 months | calendar`"
    )

    if not update.effective_message or not context.args:
        if update.effective_message:
            await update.effective_message.reply_text(usage_error, parse_mode="Markdown")
        return

    raw_text = " ".join(context.args)
    parts = [p.strip() for p in raw_text.split("|")]

    if len(parts) != 3:
        await update.effective_message.reply_text(usage_error, parse_mode="Markdown")
        return

    title, interval_raw, mode_raw = parts
    if not title:
        await update.effective_message.reply_text(usage_error, parse_mode="Markdown")
        return

    # Parse interval: e.g. "30 days", "3 months"
    interval_match = re.match(r"^(\d+)\s*(days?|months?)$", interval_raw, re.IGNORECASE)
    if not interval_match:
        await update.effective_message.reply_text(
            "❌ Invalid interval. Specify a number followed by days or months (e.g. `30 days` or `3 months`).",
            parse_mode="Markdown",
        )
        return

    interval_val = int(interval_match.group(1))
    if interval_val <= 0:
        await update.effective_message.reply_text("❌ Interval value must be greater than 0.")
        return

    # Parse mode: calendar vs elapsed
    mode_clean = mode_raw.strip().upper()
    if mode_clean in ["CALENDAR", "CAL"]:
        interval_type = Task.IntervalType.CALENDAR
    elif mode_clean in ["ELAPSED", "DYNAMIC", "DYN"]:
        interval_type = Task.IntervalType.ELAPSED
    else:
        await update.effective_message.reply_text(
            "❌ Invalid mode. Mode must be either `calendar` or `elapsed`.",
            parse_mode="Markdown",
        )
        return

    task = await sync_to_async(_sync_create_task)(title, interval_val, interval_type)

    confirm_msg = (
        f"✅ *Task #{task.id} Created!*\n\n"
        f"• *Title:* {task.title}\n"
        f"• *Mode:* {task.get_interval_type_display()}\n"
        f"• *Interval:* {task.interval_value}\n"
        f"• *Initial Due Date:* {task.next_due}\n"
    )
    await update.effective_message.reply_text(confirm_msg, parse_mode="Markdown")


def _sync_complete_task(task_id: int, notes: str):
    with transaction.atomic():
        try:
            task = Task.objects.select_for_update().get(id=task_id)
        except Task.DoesNotExist:
            return None, None

        now = timezone.now()
        history = TaskHistory.objects.create(
            task=task,
            completed_at=now,
            notes=notes,
        )

        task.last_completed = now.date()
        task.next_due = calculate_next_due(task, completion_date=now.date(), reference_date=now.date())
        task.save()
        return task, history


@authorized_only
async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /done command: /done <id> [optional notes...]"""
    usage_error = (
        "❌ *Invalid format.*\n\n"
        "*Usage:*\n"
        "`/done <id> [optional notes...]`\n\n"
        "*Example:*\n"
        "`/done 1 Replaced with 3M Filtrete filter`"
    )

    if not update.effective_message or not context.args:
        if update.effective_message:
            await update.effective_message.reply_text(usage_error, parse_mode="Markdown")
        return

    first_arg = context.args[0]
    if not first_arg.isdigit():
        await update.effective_message.reply_text(usage_error, parse_mode="Markdown")
        return

    task_id = int(first_arg)
    notes = " ".join(context.args[1:]).strip()

    result = await sync_to_async(_sync_complete_task)(task_id, notes)
    task, history = result

    if task is None:
        await update.effective_message.reply_text(f"❌ Task with ID {task_id} not found.")
        return

    notes_display = f"\n• *Notes:* {notes}" if notes else ""
    confirm_msg = (
        f"✅ *Task #{task.id} Completed!*\n\n"
        f"• *Title:* {task.title}\n"
        f"• *Completed on:* {history.completed_at.strftime('%Y-%m-%d %H:%M')}"
        f"{notes_display}\n"
        f"• *Next Due Date:* {task.next_due}"
    )
    await update.effective_message.reply_text(confirm_msg, parse_mode="Markdown")


def _sync_get_task_history(task_id: int):
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return None, None
    histories = list(task.history.all().order_by("-completed_at"))
    return task, histories


@authorized_only
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /history <id> command."""
    usage_error = "❌ *Usage:* `/history <id>`\n*Example:* `/history 1`"

    if not update.effective_message or not context.args:
        if update.effective_message:
            await update.effective_message.reply_text(usage_error, parse_mode="Markdown")
        return

    first_arg = context.args[0]
    if not first_arg.isdigit():
        await update.effective_message.reply_text(usage_error, parse_mode="Markdown")
        return

    task_id = int(first_arg)
    task, histories = await sync_to_async(_sync_get_task_history)(task_id)

    if task is None:
        await update.effective_message.reply_text(f"Task #{task_id} not found.")
        return

    if not histories:
        await update.effective_message.reply_text(
            f"No completion history recorded for task #{task.id} ({task.title})."
        )
        return

    lines = [f"📜 *Completion History for #{task.id}: {task.title}*", ""]
    for h in histories:
        date_str = h.completed_at.strftime("%Y-%m-%d %H:%M")
        notes_str = h.notes.strip() if h.notes else "(No notes provided)"
        lines.append(f"• *{date_str}*: {notes_str}")

    await _reply_chunked(update, lines)


@authorized_only
async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /export command: sends maintenance_report.md file directly."""
    if not update.effective_message:
        return

    try:
        from maintenance.services import generate_markdown_report
        report_content = await sync_to_async(generate_markdown_report)()
        task_count = await sync_to_async(Task.objects.count)()

        import io
        file_bytes = io.BytesIO(report_content.encode("utf-8"))
        file_bytes.name = "maintenance_report.md"

        caption = f"📄 Household Maintenance Report ({task_count} task{'s' if task_count != 1 else ''} recorded)"
        await update.effective_message.reply_document(
            document=file_bytes,
            filename="maintenance_report.md",
            caption=caption,
        )
    except Exception as exc:
        logger.error(f"Error generating or sending export report: {exc}", exc_info=True)
        await update.effective_message.reply_text(
            "❌ Failed to generate maintenance report. Please try again later."
        )


def create_bot_application(token: str) -> Application:
    """Build and configure the Telegram bot application with handlers."""
    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("due", due_command))
    application.add_handler(CommandHandler("add", add_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("export", export_command))

    return application

