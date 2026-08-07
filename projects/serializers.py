from django.contrib.auth import get_user_model
from rest_framework import serializers

from projects.models import Project, ProjectMembership


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("id", "name", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class ProjectMembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        source="user",
        queryset=get_user_model().objects.all(),
        write_only=True,
    )

    class Meta:
        model = ProjectMembership
        fields = ("id", "user_id", "username", "role", "created_at")
        read_only_fields = ("id", "username", "created_at")
