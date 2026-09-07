import datetime
import functools
import logging
from typing import Callable, List
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from maintenance.models import Task
from maintenance.services import get_day_countdown, format_countdown_status

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
        line_len = len(line) + 1  # newline
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


def create_bot_application(token: str) -> Application:
    """Build and configure the Telegram bot application with handlers."""
    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("due", due_command))

    return application
