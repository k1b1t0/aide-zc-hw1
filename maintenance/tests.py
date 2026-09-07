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
    add_command,
    done_command,
    history_command,
    export_command,
    create_bot_application,
)
from maintenance.models import NotificationLog, Task, TaskHistory
from maintenance.services import (
    calculate_next_due,
    evaluate_due_alerts,
    format_countdown_status,
    generate_markdown_report,
    get_day_countdown,
    mark_alert_sent,
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

    @override_settings(TELEGRAM_AUTHORIZED_USER_IDS=[123456])
    async def test_add_command_valid_and_invalid_syntax(self):
        """Verify /add creates tasks when valid and returns errors when invalid."""
        update = self._create_mock_update(user_id=123456)
        context = MagicMock()

        # Malformed format (missing pipes)
        context.args = ["Clean", "Filter", "30", "days"]
        await add_command(update, context)
        update.effective_message.reply_text.assert_called_once()
        self.assertIn("Invalid format", update.effective_message.reply_text.call_args[0][0])

        # Malformed interval
        update.effective_message.reply_text.reset_mock()
        context.args = ["Clean", "Filter", "|", "invalid_interval", "|", "elapsed"]
        await add_command(update, context)
        self.assertIn("Invalid interval", update.effective_message.reply_text.call_args[0][0])

        # Valid /add command
        update.effective_message.reply_text.reset_mock()
        context.args = ["Clean", "AC", "Filters", "|", "30", "days", "|", "elapsed"]
        await add_command(update, context)
        update.effective_message.reply_text.assert_called_once()
        resp = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Task #", resp)
        self.assertIn("Clean AC Filters", resp)
        self.assertIn("Dynamic Elapsed", resp)

        # Confirm DB creation
        task = await Task.objects.aget(title="Clean AC Filters")
        self.assertEqual(task.interval_value, 30)
        self.assertEqual(task.interval_type, Task.IntervalType.ELAPSED)
        self.assertIsNotNone(task.next_due)

    @override_settings(TELEGRAM_AUTHORIZED_USER_IDS=[123456])
    async def test_done_command_valid_and_invalid_task(self):
        """Verify /done records completion, updates next_due, and handles missing tasks."""
        update = self._create_mock_update(user_id=123456)
        context = MagicMock()

        # Invalid task ID format
        context.args = ["abc"]
        await done_command(update, context)
        self.assertIn("Invalid format", update.effective_message.reply_text.call_args[0][0])

        # Non-existent task ID
        update.effective_message.reply_text.reset_mock()
        context.args = ["9999"]
        await done_command(update, context)
        self.assertIn("Task with ID 9999 not found", update.effective_message.reply_text.call_args[0][0])

        # Create real task
        task = await Task.objects.acreate(
            title="Clean Microwave",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=14,
            next_due=timezone.now().date(),
        )

        update.effective_message.reply_text.reset_mock()
        context.args = [str(task.id), "Steam", "cleaned", "with", "lemon"]
        await done_command(update, context)
        update.effective_message.reply_text.assert_called_once()
        resp = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Completed!", resp)
        self.assertIn("Steam cleaned with lemon", resp)

        # Check DB updates
        updated_task = await Task.objects.aget(id=task.id)
        self.assertEqual(updated_task.last_completed, timezone.now().date())
        self.assertEqual(updated_task.next_due, timezone.now().date() + datetime.timedelta(days=14))

        history = await TaskHistory.objects.filter(task=updated_task).afirst()
        self.assertIsNotNone(history)
        self.assertEqual(history.notes, "Steam cleaned with lemon")

    @override_settings(TELEGRAM_AUTHORIZED_USER_IDS=[123456])
    async def test_history_command_missing_empty_and_populated(self):
        """Verify /history handles missing ID, empty history, and multiple entries."""
        update = self._create_mock_update(user_id=123456)
        context = MagicMock()

        # Non-existent task ID
        context.args = ["8888"]
        await history_command(update, context)
        update.effective_message.reply_text.assert_called_with("Task #8888 not found.")

        # Create task without history
        task = await Task.objects.acreate(
            title="Clean Windows",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=30,
        )
        update.effective_message.reply_text.reset_mock()
        context.args = [str(task.id)]
        await history_command(update, context)
        self.assertIn("No completion history recorded", update.effective_message.reply_text.call_args[0][0])

        # Add history entries
        await TaskHistory.objects.acreate(
            task=task,
            completed_at=timezone.now(),
            notes="Living room only",
        )
        update.effective_message.reply_text.reset_mock()
        await history_command(update, context)
        resp = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Living room only", resp)
        self.assertIn(f"Completion History for #{task.id}: Clean Windows", resp)

    @override_settings(TELEGRAM_AUTHORIZED_USER_IDS=[123456])
    async def test_export_command_sends_markdown_document(self):
        """Verify /export generates report and calls reply_document."""
        update = self._create_mock_update(user_id=123456)
        update.effective_message.reply_document = AsyncMock()
        context = MagicMock()

        await Task.objects.acreate(
            title="Test Task Export",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=10,
        )

        await export_command(update, context)

        update.effective_message.reply_document.assert_called_once()
        kwargs = update.effective_message.reply_document.call_args[1]
        self.assertEqual(kwargs["filename"], "maintenance_report.md")
        self.assertIn("Household Maintenance Report", kwargs["caption"])
        doc_bytes = kwargs["document"].getvalue().decode("utf-8")
        self.assertIn("# Household Maintenance Report", doc_bytes)
        self.assertIn("Test Task Export", doc_bytes)


class ProactiveNotificationsAndAlertsTests(TestCase):
    def test_evaluate_due_alerts_triggers_and_deduplicates(self):
        """Verify evaluate_due_alerts identifies T-3, T-1, Overdue and respects NotificationLog."""
        ref_today = datetime.date(2026, 9, 10)

        # T-3 task (due in 3 days)
        t_3 = Task.objects.create(
            title="Clean Fridge Coils",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=90,
            next_due=ref_today + datetime.timedelta(days=3),
        )
        # T-1 task (due tomorrow)
        t_1 = Task.objects.create(
            title="Replace Water Filter",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=60,
            next_due=ref_today + datetime.timedelta(days=1),
        )
        # Overdue task
        t_overdue = Task.objects.create(
            title="Test Smoke Alarms",
            interval_type=Task.IntervalType.CALENDAR,
            interval_value=6,
            next_due=ref_today - datetime.timedelta(days=2),
        )
        # Task due in 10 days (no alert)
        t_future = Task.objects.create(
            title="Deep Clean Oven",
            interval_type=Task.IntervalType.ELAPSED,
            interval_value=30,
            next_due=ref_today + datetime.timedelta(days=10),
        )

        alerts = evaluate_due_alerts(reference_date=ref_today)
        self.assertEqual(len(alerts), 3)

        alert_tasks = [item[0] for item in alerts]
        self.assertIn(t_3, alert_tasks)
        self.assertIn(t_1, alert_tasks)
        self.assertIn(t_overdue, alert_tasks)
        self.assertNotIn(t_future, alert_tasks)

        # Mark alerts as sent
        for task, alert_type, _ in alerts:
            mark_alert_sent(task, alert_type, task.next_due)

        # Running evaluate again for same cycle returns 0 alerts
        alerts_second_run = evaluate_due_alerts(reference_date=ref_today)
        self.assertEqual(len(alerts_second_run), 0)

        # Complete / clean up other tasks so they aren't overdue at new_ref
        t_1.delete()
        t_overdue.delete()
        t_future.delete()

        # When task is rescheduled for next cycle, new cycle allows new alerts
        t_3.next_due = ref_today + datetime.timedelta(days=93)
        t_3.save()
        # Pretend today advances to 90 days later (so t_3 is again due in 3 days)
        new_ref = t_3.next_due - datetime.timedelta(days=3)
        new_cycle_alerts = evaluate_due_alerts(reference_date=new_ref)
        self.assertEqual(len(new_cycle_alerts), 1)
        self.assertEqual(new_cycle_alerts[0][0], t_3)
        self.assertEqual(new_cycle_alerts[0][1], NotificationLog.AlertType.T3)


