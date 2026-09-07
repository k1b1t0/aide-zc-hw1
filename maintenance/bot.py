import functools
import logging
from typing import Callable
from django.conf import settings
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

logger = logging.getLogger(__name__)


def authorized_only(func: Callable) -> Callable:
    """Decorator to ensure only configured authorized user IDs can execute bot commands."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        authorized_ids = getattr(settings, "TELEGRAM_AUTHORIZED_USER_IDS", [])
        # If authorized_ids is configured and user is not authorized, reject access
        if authorized_ids and (not user or user.id not in authorized_ids):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ Access Denied: You are not authorized to use this maintenance bot."
                )
            return
        return await func(update, context, *args, **kwargs)

    return wrapper


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


def create_bot_application(token: str) -> Application:
    """Build and configure the Telegram bot application with handlers."""
    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    return application
