from django.db import models

from projects.models import Project, ProjectMembership


class Quest(models.Model):
    class State(models.TextChoices):
        BACKLOG = "BACKLOG", "Backlog"
        READY = "READY", "Ready"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        REVIEW = "REVIEW", "Review"
        DONE = "DONE", "Done"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="quests")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.BACKLOG)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.MEDIUM)
    due_date = models.DateField(null=True, blank=True)
    assignee = models.ForeignKey(
        ProjectMembership,
        on_delete=models.PROTECT,
        related_name="assigned_quests",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.title
