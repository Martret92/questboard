from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from projects.models import Project
from quests.models import Quest
from quests.serializers import QuestSerializer
from quests.services import QuestMutationError, assign_quest, create_quest, delete_quest, update_quest_metadata


class QuestViewSet(viewsets.ViewSet):
    def _project(self, project_pk: int) -> Project:
        return get_object_or_404(
            Project.objects.filter(memberships__user=self.request.user).distinct(),
            pk=project_pk,
        )

    def _quest(self, project: Project, pk: int) -> Quest:
        return get_object_or_404(
            Quest.objects.select_related("assignee", "assignee__user").filter(project=project),
            pk=pk,
        )

    def list(self, request, project_pk=None):
        project = self._project(project_pk)
        queryset = Quest.objects.filter(project=project).select_related("assignee", "assignee__user").order_by("id")

        state = request.query_params.get("state")
        priority = request.query_params.get("priority")
        assignee_id = request.query_params.get("assignee")
        if state:
            queryset = queryset.filter(state=state)
        if priority:
            queryset = queryset.filter(priority=priority)
        if assignee_id:
            queryset = queryset.filter(assignee_id=assignee_id)

        return Response(QuestSerializer(queryset, many=True).data)

    def retrieve(self, request, pk=None, project_pk=None):
        project = self._project(project_pk)
        return Response(QuestSerializer(self._quest(project, pk)).data)

    def create(self, request, project_pk=None):
        project = self._project(project_pk)
        serializer = QuestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            quest = create_quest(
                project_id=project.id,
                actor=request.user,
                title=serializer.validated_data["title"],
                description=serializer.validated_data.get("description", ""),
                priority=serializer.validated_data.get("priority", Quest.Priority.MEDIUM),
                due_date=serializer.validated_data.get("due_date"),
                assignee_id=serializer.validated_data.get("assignee_id"),
            )
        except QuestMutationError as exc:
            message = exc.messages[0]
            if "Only owners or reviewers" in message:
                raise PermissionDenied(message) from exc
            raise ValidationError({"detail": message}) from exc
        return Response(QuestSerializer(quest).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None, project_pk=None):
        project = self._project(project_pk)
        quest = self._quest(project, pk)
        serializer = QuestSerializer(quest, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            metadata_fields = {key: serializer.validated_data[key] for key in ("title", "description", "priority", "due_date") if key in serializer.validated_data}
            if metadata_fields:
                quest = update_quest_metadata(quest_id=quest.id, actor=request.user, **metadata_fields)
            if "assignee_id" in serializer.validated_data:
                quest = assign_quest(
                    quest_id=quest.id,
                    actor=request.user,
                    assignee_id=serializer.validated_data["assignee_id"],
                )
        except QuestMutationError as exc:
            message = exc.messages[0]
            if "Only owners or reviewers" in message:
                raise PermissionDenied(message) from exc
            raise ValidationError({"detail": message}) from exc

        return Response(QuestSerializer(quest).data)

    def destroy(self, request, pk=None, project_pk=None):
        project = self._project(project_pk)
        quest = self._quest(project, pk)
        try:
            delete_quest(quest_id=quest.id, actor=request.user)
        except QuestMutationError as exc:
            message = exc.messages[0]
            if "Only owners or reviewers" in message:
                raise PermissionDenied(message) from exc
            raise ValidationError({"detail": message}) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)
