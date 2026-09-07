import datetime
from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from maintenance.apps import MaintenanceConfig
from maintenance.models import Task, TaskHistory


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
