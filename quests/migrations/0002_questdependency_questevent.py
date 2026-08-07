import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0001_initial"),
        ("quests", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="QuestDependency",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("dependent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dependency_edges", to="quests.quest")),
                ("prerequisite", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dependent_edges", to="quests.quest")),
            ],
        ),
        migrations.CreateModel(
            name="QuestEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quest_id_snapshot", models.BigIntegerField()),
                ("event_type", models.CharField(choices=[("QUEST_CREATED", "Quest created"), ("ASSIGNEE_CHANGED", "Assignee changed"), ("DEPENDENCY_ADDED", "Dependency added"), ("DEPENDENCY_REMOVED", "Dependency removed"), ("STATE_CHANGED", "State changed")], max_length=32)),
                ("data", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="quest_events", to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="quest_events", to="projects.project")),
                ("quest", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="events", to="quests.quest")),
            ],
        ),
        migrations.AddConstraint(
            model_name="questdependency",
            constraint=models.UniqueConstraint(fields=("dependent", "prerequisite"), name="uniq_quest_dependency_edge"),
        ),
        migrations.AddConstraint(
            model_name="questdependency",
            constraint=models.CheckConstraint(condition=~Q(dependent=F("prerequisite")), name="quest_dependency_not_self"),
        ),
        migrations.AddIndex(
            model_name="questevent",
            index=models.Index(fields=["project", "quest_id_snapshot", "created_at"], name="quest_event_lookup_idx"),
        ),
    ]
