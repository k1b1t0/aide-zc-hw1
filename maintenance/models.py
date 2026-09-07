from django.db import models
from django.utils import timezone


class Task(models.Model):
    class IntervalType(models.TextChoices):
        CALENDAR = "CALENDAR", "Strict Calendar"
        ELAPSED = "ELAPSED", "Dynamic Elapsed"

    title = models.CharField(max_length=255)
    interval_type = models.CharField(
        max_length=20,
        choices=IntervalType.choices,
        default=IntervalType.ELAPSED,
    )
    interval_value = models.PositiveIntegerField(
        help_text="Recurrence interval value (e.g. number of days or months)",
    )
    last_completed = models.DateField(null=True, blank=True)
    next_due = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"[{self.id}] {self.title} ({self.get_interval_type_display()}: {self.interval_value})"


class TaskHistory(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="history",
    )
    completed_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"History #{self.id} for Task #{self.task_id} at {self.completed_at:%Y-%m-%d %H:%M}"
