from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from projects.models import Project, ProjectMembership
from projects.serializers import ProjectMembershipSerializer, ProjectSerializer
from projects.services import (
    ProjectMembershipError,
    add_membership,
    change_membership_role,
    create_project,
    remove_membership,
)


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.filter(memberships__user=self.request.user).distinct().order_by("id")

    def perform_create(self, serializer):
        project = create_project(
            actor=self.request.user,
            name=serializer.validated_data["name"],
            description=serializer.validated_data.get("description", ""),
        )
        serializer.instance = project

    def perform_update(self, serializer):
        project = self.get_object()
        if not project.memberships.filter(
            user=self.request.user,
            role=ProjectMembership.Role.OWNER,
        ).exists():
            raise PermissionDenied("Only project owners can update project metadata.")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        raise PermissionDenied("Project deletion is not part of the MVP scope.")


class ProjectMembershipViewSet(viewsets.ViewSet):
    def _project(self, project_pk: int) -> Project:
        return get_object_or_404(
            Project.objects.filter(memberships__user=self.request.user).distinct(),
            pk=project_pk,
        )

    def list(self, request, project_pk=None):
        project = self._project(project_pk)
        memberships = project.memberships.select_related("user").order_by("id")
        return Response(ProjectMembershipSerializer(memberships, many=True).data)

    def retrieve(self, request, pk=None, project_pk=None):
        project = self._project(project_pk)
        membership = get_object_or_404(project.memberships.select_related("user"), pk=pk)
        return Response(ProjectMembershipSerializer(membership).data)

    def create(self, request, project_pk=None):
        project = self._project(project_pk)
        serializer = ProjectMembershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            membership = add_membership(
                project_id=project.id,
                actor=request.user,
                user_id=serializer.validated_data["user"].id,
                role=serializer.validated_data["role"],
            )
        except ProjectMembershipError as exc:
            raise PermissionDenied(exc.messages[0]) from exc
        except IntegrityError as exc:
            raise ValidationError({"user_id": "User is already a member of this project."}) from exc
        return Response(ProjectMembershipSerializer(membership).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None, project_pk=None):
        project = self._project(project_pk)
        membership = get_object_or_404(project.memberships, pk=pk)
        serializer = ProjectMembershipSerializer(membership, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if set(serializer.validated_data) - {"role"}:
            raise ValidationError("Only role can be changed on an existing membership.")
        if "role" not in serializer.validated_data:
            return Response(ProjectMembershipSerializer(membership).data)
        try:
            membership = change_membership_role(
                membership_id=membership.id,
                actor=request.user,
                role=serializer.validated_data["role"],
            )
        except ProjectMembershipError as exc:
            message = exc.messages[0]
            if "Only project owners" in message:
                raise PermissionDenied(message) from exc
            raise ValidationError({"role": message}) from exc
        return Response(ProjectMembershipSerializer(membership).data)

    def destroy(self, request, pk=None, project_pk=None):
        project = self._project(project_pk)
        membership = get_object_or_404(project.memberships, pk=pk)
        try:
            remove_membership(membership_id=membership.id, actor=request.user)
        except ProjectMembershipError as exc:
            message = exc.messages[0]
            if "Only project owners" in message:
                raise PermissionDenied(message) from exc
            raise ValidationError({"detail": message}) from exc
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)
