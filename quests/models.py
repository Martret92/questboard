from django.conf import settings
from django.db import models
from django.db.models import F, Q

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


class QuestDependency(models.Model):
    dependent = models.ForeignKey(Quest, on_delete=models.CASCADE, related_name="dependency_edges")
    prerequisite = models.ForeignKey(Quest, on_delete=models.CASCADE, related_name="dependent_edges")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("dependent", "prerequisite"),
                name="uniq_quest_dependency_edge",
            ),
            models.CheckConstraint(
                condition=~Q(dependent=F("prerequisite")),
                name="quest_dependency_not_self",
            ),
        ]


class QuestEvent(models.Model):
    class Type(models.TextChoices):
        QUEST_CREATED = "QUEST_CREATED", "Quest created"
        ASSIGNEE_CHANGED = "ASSIGNEE_CHANGED", "Assignee changed"
        DEPENDENCY_ADDED = "DEPENDENCY_ADDED", "Dependency added"
        DEPENDENCY_REMOVED = "DEPENDENCY_REMOVED", "Dependency removed"
        STATE_CHANGED = "STATE_CHANGED", "State changed"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="quest_events")
    quest = models.ForeignKey(
        Quest,
        on_delete=models.SET_NULL,
        related_name="events",
        null=True,
        blank=True,
    )
    quest_id_snapshot = models.BigIntegerField()
    event_type = models.CharField(max_length=32, choices=Type.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="quest_events",
        null=True,
        blank=True,
    )
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=("project", "quest_id_snapshot", "created_at"), name="quest_event_lookup_idx"),
        ]
