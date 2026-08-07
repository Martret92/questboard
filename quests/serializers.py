from rest_framework import serializers

from quests.models import Quest, QuestDependency, QuestEvent


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


class QuestDependencySerializer(serializers.ModelSerializer):
    prerequisite_id = serializers.IntegerField()

    class Meta:
        model = QuestDependency
        fields = ("id", "dependent", "prerequisite_id", "created_at")
        read_only_fields = ("id", "dependent", "created_at")


class QuestTransitionSerializer(serializers.Serializer):
    target_state = serializers.ChoiceField(choices=Quest.State.choices)


class QuestEventSerializer(serializers.ModelSerializer):
    actor_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = QuestEvent
        fields = (
            "id",
            "quest_id_snapshot",
            "event_type",
            "actor_id",
            "data",
            "created_at",
        )
        read_only_fields = fields
