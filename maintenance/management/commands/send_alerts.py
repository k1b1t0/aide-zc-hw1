import asyncio
import logging
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from telegram import Bot

from maintenance.services import evaluate_due_alerts, mark_alert_sent

logger = logging.getLogger(__name__)


async def _send_telegram_alert(token: str, chat_id: int, message: str) -> None:
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")


class Command(BaseCommand):
    help = "Evaluate due tasks and send proactive maintenance alerts (T-3, T-1, Overdue) via Telegram."

    def handle(self, *args, **options):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        authorized_ids = getattr(settings, "TELEGRAM_AUTHORIZED_USER_IDS", [])

        alerts = evaluate_due_alerts()
        self.stdout.write(f"Found {len(alerts)} pending alert(s).")

        if not alerts:
            self.stdout.write(self.style.SUCCESS("No pending alerts to dispatch."))
            return

        if not token or not authorized_ids:
            self.stdout.write(
                self.style.WARNING(
                    "Telegram token or authorized user IDs not configured. Logging alerts without dispatch."
                )
            )

        for task, alert_type, message in alerts:
            self.stdout.write(f"Sending [{alert_type}] for task #{task.id}: {task.title}")

            if token and authorized_ids:
                for uid in authorized_ids:
                    try:
                        asyncio.run(_send_telegram_alert(token, uid, message))
                    except Exception as exc:
                        self.stderr.write(
                            self.style.ERROR(f"Failed to send alert to user {uid}: {exc}")
                        )

            # Record in notification log
            mark_alert_sent(task, alert_type, task.next_due)

        self.stdout.write(self.style.SUCCESS(f"Successfully processed {len(alerts)} alert(s)."))
