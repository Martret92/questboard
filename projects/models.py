from django.conf import settings
from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class ProjectMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        REVIEWER = "REVIEWER", "Reviewer"
        CONTRIBUTOR = "CONTRIBUTOR", "Contributor"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=16, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("project", "user"), name="uniq_project_membership_user"),
        ]

    def __str__(self) -> str:
        return f"{self.project_id}:{self.user_id}:{self.role}"
