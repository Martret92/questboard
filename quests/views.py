from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from projects.models import Project
from quests.models import Quest, QuestDependency, QuestEvent
from quests.serializers import (
    QuestDependencySerializer,
    QuestEventSerializer,
    QuestSerializer,
    QuestTransitionSerializer,
)
from quests.services import (
    QuestMutationError,
    add_dependency,
    create_quest,
    delete_quest,
    remove_dependency,
    transition_quest,
    update_quest,
)


def _raise_api_error(exc: QuestMutationError):
    message = exc.messages[0]
    if "Only owners or reviewers" in message:
        raise PermissionDenied(message) from exc
    raise ValidationError({"detail": message}) from exc


class ProjectScopedMixin:
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


class QuestViewSet(ProjectScopedMixin, viewsets.ViewSet):
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
            _raise_api_error(exc)
        return Response(QuestSerializer(quest).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None, project_pk=None):
        project = self._project(project_pk)
        quest = self._quest(project, pk)
        serializer = QuestSerializer(quest, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        changes = {
            key: serializer.validated_data[key]
            for key in ("title", "description", "priority", "due_date", "assignee_id")
            if key in serializer.validated_data
        }
        try:
            quest = update_quest(quest_id=quest.id, actor=request.user, **changes)
        except QuestMutationError as exc:
            _raise_api_error(exc)
        return Response(QuestSerializer(quest).data)

    def destroy(self, request, pk=None, project_pk=None):
        project = self._project(project_pk)
        quest = self._quest(project, pk)
        try:
            delete_quest(quest_id=quest.id, actor=request.user)
        except QuestMutationError as exc:
            _raise_api_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class QuestDependencyViewSet(ProjectScopedMixin, viewsets.ViewSet):
    def list(self, request, project_pk=None, quest_pk=None):
        project = self._project(project_pk)
        quest = self._quest(project, quest_pk)
        edges = QuestDependency.objects.filter(dependent=quest).select_related("prerequisite").order_by("id")
        return Response(QuestDependencySerializer(edges, many=True).data)

    def create(self, request, project_pk=None, quest_pk=None):
        project = self._project(project_pk)
        quest = self._quest(project, quest_pk)
        serializer = QuestDependencySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            edge = add_dependency(
                dependent_id=quest.id,
                prerequisite_id=serializer.validated_data["prerequisite_id"],
                actor=request.user,
            )
        except QuestMutationError as exc:
            _raise_api_error(exc)
        return Response(QuestDependencySerializer(edge).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None, project_pk=None, quest_pk=None):
        project = self._project(project_pk)
        quest = self._quest(project, quest_pk)
        edge = get_object_or_404(QuestDependency.objects.filter(dependent=quest), pk=pk)
        try:
            remove_dependency(dependency_id=edge.id, actor=request.user)
        except QuestMutationError as exc:
            _raise_api_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class QuestTransitionView(ProjectScopedMixin, viewsets.ViewSet):
    def create(self, request, project_pk=None, quest_pk=None):
        project = self._project(project_pk)
        quest = self._quest(project, quest_pk)
        serializer = QuestTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            quest = transition_quest(
                quest_id=quest.id,
                actor=request.user,
                target_state=serializer.validated_data["target_state"],
            )
        except QuestMutationError as exc:
            _raise_api_error(exc)
        return Response(QuestSerializer(quest).data)


class QuestEventView(ProjectScopedMixin, viewsets.ViewSet):
    def list(self, request, project_pk=None, quest_pk=None):
        project = self._project(project_pk)
        events = QuestEvent.objects.filter(
            project=project,
            quest_id_snapshot=quest_pk,
        ).select_related("actor").order_by("created_at", "id")
        return Response(QuestEventSerializer(events, many=True).data)
