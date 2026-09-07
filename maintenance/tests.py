import datetime
from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from maintenance.apps import MaintenanceConfig
from maintenance.models import Task, TaskHistory
from maintenance.services import (
    calculate_next_due,
    get_day_countdown,
    format_countdown_status,
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
        # Completed on 2026-05-28 (early)
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
        # Completed on 2026-04-10 (3 months late)
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
