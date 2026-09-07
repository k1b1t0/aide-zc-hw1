import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from django.apps import apps
from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from maintenance.apps import MaintenanceConfig
from maintenance.bot import (
    authorized_only,
    help_command,
    start_command,
    list_command,
    due_command,
    create_bot_application,
)
from maintenance.models import Task, TaskHistory
from maintenance.services import (
    calculate_next_due,
    format_countdown_status,
    generate_markdown_report,
    get_day_countdown,
)


class ProjectSetupSmokeTest(TestCase):
    def test_app_is_installed(self):
        """Verify that the maintenance application is properly registered in INSTALLED_APPS."""
        self.assertIn("maintenance", [app.name for app in apps.get_app_configs()])
        self.assertEqual(apps.get_app_config("maintenance").name, MaintenanceConfig.name)

    def test_smoke_pass(self):
        """Sanity check that the Django test runner is functional."""
        self.assertTrue(True)


class TaskAndHistoryModelTests(TestCase):
    def test_create_task_with_default_and_custom_fields(self):
        """Verify creating a Task with calendar and elapsed types and field constraints."""
        task = Task.objects.create(
            title="Clean Heat Pump Filter",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=60,
            last_completed=datetime.date(2026, 8, 1),
            next_due=datetime.date(2026, 9, 30),
        )
        self.assertEqual(task.title, "Clean Heat Pump Filter")
        self.assertEqual(task.interval_type, Task.IntervalType.ELAPSED)
        self.assertEqual(task.interval_value, 60)
        self.assertEqual(task.last_completed, datetime.date(2026, 8, 1))
        self.assertEqual(task.next_due, datetime.date(2026, 9, 30))
        self.assertIsNotNone(task.created_at)
        self.assertIn("Clean Heat Pump Filter", str(task))

    def test_create_task_with_calendar_mode(self):
        task = Task.objects.create(
            title="Smoke Detector Check",
            interval_type=Task.IntervalType.CALENDAR,
            interval_value=6,
        )
        self.assertIsNone(task.last_completed)
        self.assertIsNone(task.next_due)
        self.assertIn("Smoke Detector Check", str(task))

    def test_create_task_history_and_relationship(self):
        """Verify TaskHistory relationship, ordering, and cascade deletion."""
        task = Task.objects.create(
            title="Descale Coffee Machine",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=30,
        )
        now = timezone.now()
        history1 = TaskHistory.objects.create(
            task=task,
            completed_at=now,
            notes="Used vinegar solution",
        )
        history2 = TaskHistory.objects.create(
            task=task,
            completed_at=now,
            notes="",
        )

        self.assertEqual(task.history.count(), 2)
        self.assertIn(history1, task.history.all())
        self.assertIn(history2, task.history.all())
        self.assertIn(f"History #{history1.id}", str(history1))

        # Test CASCADE delete
        task_id = task.id
        task.delete()
        self.assertEqual(Task.objects.filter(id=task_id).count(), 0)
        self.assertEqual(TaskHistory.objects.filter(task_id=task_id).count(), 0)


class RecalculationDomainServiceTests(TestCase):
    def test_elapsed_mode_calculation(self):
        """Verify ELAPSED mode calculates exactly interval_value days from completion_date."""
        task = Task(interval_type=Task.IntervalType.ELAPSED, interval_value=30)
        completed_date = datetime.date(2026, 3, 15)
        next_due = calculate_next_due(task, completion_date=completed_date)
        self.assertEqual(next_due, datetime.date(2026, 4, 14))

    def test_calendar_mode_calculation_on_time(self):
        """Verify CALENDAR mode advances by fixed cadence."""
        task = Task(
            interval_type=Task.IntervalType.CALENDAR,
            interval_value=3,  # 3 months
            next_due=datetime.date(2026, 6, 1),
        )
        next_due = calculate_next_due(
            task,
            completion_date=datetime.date(2026, 5, 28),
            reference_date=datetime.date(2026, 5, 28),
        )
        self.assertEqual(next_due, datetime.date(2026, 9, 1))

    def test_calendar_mode_overdue_advancement(self):
        """Verify that completing overdue task advances past the completion date."""
        task = Task(
            interval_type=Task.IntervalType.CALENDAR,
            interval_value=1,  # monthly
            next_due=datetime.date(2026, 1, 15),
        )
        next_due = calculate_next_due(
            task,
            completion_date=datetime.date(2026, 4, 10),
            reference_date=datetime.date(2026, 4, 10),
        )
        self.assertGreater(next_due, datetime.date(2026, 4, 10))
        self.assertEqual(next_due, datetime.date(2026, 4, 15))

    def test_month_end_and_leap_year_edge_cases(self):
        """Verify Jan 31 + 1 month rolls to Feb 28/29 without ValueError."""
        task = Task(
            interval_type=Task.IntervalType.CALENDAR,
            interval_value=1,
            next_due=datetime.date(2026, 1, 31),
        )
        next_due = calculate_next_due(
            task,
            completion_date=datetime.date(2026, 1, 31),
            reference_date=datetime.date(2026, 1, 31),
        )
        self.assertEqual(next_due, datetime.date(2026, 2, 28))

        # Leap year 2028
        task_leap = Task(
            interval_type=Task.IntervalType.CALENDAR,
            interval_value=1,
            next_due=datetime.date(2028, 1, 31),
        )
        next_due_leap = calculate_next_due(
            task_leap,
            completion_date=datetime.date(2028, 1, 31),
            reference_date=datetime.date(2028, 1, 31),
        )
        self.assertEqual(next_due_leap, datetime.date(2028, 2, 29))

    def test_day_countdown_and_formatting(self):
        """Verify get_day_countdown and format_countdown_status across states."""
        ref = datetime.date(2026, 9, 10)

        # Future
        future = datetime.date(2026, 9, 15)
        cd_future = get_day_countdown(future, reference_date=ref)
        self.assertEqual(cd_future, 5)
        self.assertEqual(format_countdown_status(cd_future), "Due in 5 days")

        # Today
        today = datetime.date(2026, 9, 10)
        cd_today = get_day_countdown(today, reference_date=ref)
        self.assertEqual(cd_today, 0)
        self.assertEqual(format_countdown_status(cd_today), "Due today")

        # Overdue
        past = datetime.date(2026, 9, 7)
        cd_past = get_day_countdown(past, reference_date=ref)
        self.assertEqual(cd_past, -3)
        self.assertEqual(format_countdown_status(cd_past), "Overdue by 3 days")

        # None
        self.assertIsNone(get_day_countdown(None))
        self.assertEqual(format_countdown_status(None), "Not scheduled")


class MarkdownReportServiceTests(TestCase):
    def test_empty_database_report(self):
        """Verify report structure and empty messages when no tasks exist."""
        report = generate_markdown_report()
        self.assertIn("# Household Maintenance Report", report)
        self.assertIn("Generated on:", report)
        self.assertIn("UTC", report)
        self.assertIn("## Overdue Tasks", report)
        self.assertIn("## Upcoming Tasks", report)
        self.assertIn("## Completion History", report)
        self.assertIn("_No maintenance tasks recorded._", report)

    def test_populated_report_with_overdue_and_upcoming(self):
        """Verify overdue, upcoming tables, null dates, and sanitization."""
        ref_today = datetime.date(2026, 9, 10)

        t_overdue = Task.objects.create(
            title="Clean Filter | Left & Right",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=30,
            next_due=datetime.date(2026, 9, 5),
        )
        t_upcoming = Task.objects.create(
            title="Oil Chainsaw",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=60,
            next_due=datetime.date(2026, 9, 20),
        )
        t_none = Task.objects.create(
            title="Inspect Roof",
            interval_type=Task.IntervalType.CALENDAR,
            interval_value=12,
            next_due=None,
        )

        TaskHistory.objects.create(
            task=t_overdue,
            completed_at=timezone.make_aware(datetime.datetime(2026, 8, 5, 14, 30)),
            notes="Line 1\nLine 2 | with pipe",
        )

        report = generate_markdown_report(reference_date=ref_today)

        self.assertIn("# Household Maintenance Report", report)
        self.assertIn("| Task ID | Title | Recurrence | Next Due Date | Days Overdue |", report)
        self.assertIn(f"| {t_overdue.id} | Clean Filter \\| Left & Right |", report)
        self.assertIn("5 |", report)
        self.assertIn("| Task ID | Title | Recurrence | Next Due Date | Days Remaining |", report)
        self.assertIn(f"| {t_upcoming.id} | Oil Chainsaw |", report)
        self.assertIn("10 |", report)
        self.assertIn(f"| {t_none.id} | Inspect Roof |", report)
        self.assertIn("N/A |", report)
        self.assertIn(f"### Task #{t_overdue.id}: Clean Filter \\| Left & Right", report)
        self.assertIn("Line 1 Line 2 \\| with pipe", report)


class TelegramBotClientAndAuthTests(TestCase):
    def _create_mock_update(self, user_id: int):
        update = MagicMock()
        user = MagicMock()
        user.id = user_id
        update.effective_user = user
        message = AsyncMock()
        update.effective_message = message
        return update

    @override_settings(TELEGRAM_AUTHORIZED_USER_IDS=[123456])
    async def test_authorized_user_can_access_start_command(self):
        """Authorized user gets welcome message from /start."""
        update = self._create_mock_update(user_id=123456)
        context = MagicMock()

        await start_command(update, context)

        update.effective_message.reply_text.assert_called_once()
        call_args = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Welcome to the Household Maintenance Tracker Bot!", call_args)

    @override_settings(TELEGRAM_AUTHORIZED_USER_IDS=[123456])
    async def test_unauthorized_user_is_rejected(self):
        """Unauthorized user receives access denied."""
        update = self._create_mock_update(user_id=999999)
        context = MagicMock()

        await start_command(update, context)

        update.effective_message.reply_text.assert_called_once()
        call_args = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Access Denied", call_args)

    @override_settings(TELEGRAM_AUTHORIZED_USER_IDS=[123456])
    async def test_help_command_lists_all_commands(self):
        """Authorized user gets full command reference from /help."""
        update = self._create_mock_update(user_id=123456)
        context = MagicMock()

        await help_command(update, context)

        update.effective_message.reply_text.assert_called_once()
        call_args = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("/start", call_args)
        self.assertIn("/help", call_args)
        self.assertIn("/list", call_args)
        self.assertIn("/due", call_args)
        self.assertIn("/add", call_args)
        self.assertIn("/done", call_args)
        self.assertIn("/history", call_args)
        self.assertIn("/export", call_args)

    def test_create_bot_application(self):
        """Verify bot application builds with registered handlers."""
        app = create_bot_application("dummy_token")
        self.assertIsNotNone(app)

    @override_settings(TELEGRAM_AUTHORIZED_USER_IDS=[123456])
    async def test_list_command_empty_and_populated(self):
        """Verify /list output for empty DB and populated tasks."""
        update = self._create_mock_update(user_id=123456)
        context = MagicMock()

        # Empty state
        await list_command(update, context)
        update.effective_message.reply_text.assert_called_with(
            "No maintenance tasks found. Use /add to create one."
        )

        # Create tasks
        t1 = await Task.objects.acreate(
            title="Clean HVAC Filters",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=90,
            next_due=timezone.now().date() + datetime.timedelta(days=4),
        )
        update.effective_message.reply_text.reset_mock()

        await list_command(update, context)
        update.effective_message.reply_text.assert_called_once()
        response_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn(f"[{t1.id}] *Clean HVAC Filters*", response_text)
        self.assertIn("Due in 4 days", response_text)

    @override_settings(TELEGRAM_AUTHORIZED_USER_IDS=[123456])
    async def test_due_command_filters_overdue_and_near_due(self):
        """Verify /due filters only overdue and tasks due within 7 days."""
        update = self._create_mock_update(user_id=123456)
        context = MagicMock()
        today = timezone.now().date()

        # Empty state
        await due_command(update, context)
        update.effective_message.reply_text.assert_called_with(
            "All caught up! No tasks due in the next 7 days."
        )

        # Overdue task
        t_overdue = await Task.objects.acreate(
            title="Check Fire Extinguisher",
            interval_type=Task.IntervalType.CALENDAR,
            interval_value=6,
            next_due=today - datetime.timedelta(days=2),
        )
        # Due in 3 days (within 7 days)
        t_near = await Task.objects.acreate(
            title="Water Garden Herbs",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=7,
            next_due=today + datetime.timedelta(days=3),
        )
        # Due in 20 days (outside 7 days)
        t_far = await Task.objects.acreate(
            title="Service Lawn Mower",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=60,
            next_due=today + datetime.timedelta(days=20),
        )

        update.effective_message.reply_text.reset_mock()
        await due_command(update, context)

        update.effective_message.reply_text.assert_called_once()
        response_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn(f"OVERDUE by 2 days*: [{t_overdue.id}] Check Fire Extinguisher", response_text)
        self.assertIn(f"Due in 3 days*: [{t_near.id}] Water Garden Herbs", response_text)
        self.assertNotIn("Service Lawn Mower", response_text)
