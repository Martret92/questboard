from rest_framework import serializers

from quests.models import Quest


class QuestSerializer(serializers.ModelSerializer):
    assignee_id = serializers.IntegerField(allow_null=True, required=False)

    class Meta:
        model = Quest
        fields = (
            "id",
            "project",
            "title",
            "description",
            "state",
            "priority",
            "due_date",
            "assignee_id",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "project", "state", "created_at", "updated_at")
