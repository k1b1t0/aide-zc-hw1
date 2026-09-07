import logging
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from maintenance.bot import create_bot_application

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Household Maintenance Telegram Bot in long-polling mode."

    def handle(self, *args, **options):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        if not token:
            raise CommandError(
                "TELEGRAM_BOT_TOKEN environment variable or setting is not configured."
            )

        self.stdout.write(self.style.SUCCESS("Starting Telegram bot in polling mode..."))
        app = create_bot_application(token)

        try:
            # run_polling runs until interrupted (SIGINT, SIGTERM)
            app.run_polling()
        except KeyboardInterrupt:
            self.stdout.write(self.style.NOTICE("Bot stopped by user (SIGINT)."))
        except Exception as exc:
            raise CommandError(f"Bot encountered an error: {exc}") from exc
        finally:
            self.stdout.write(self.style.SUCCESS("Bot shutdown complete."))
