from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from projects.models import Project, ProjectMembership


class ProjectMembershipError(ValidationError):
    pass


@transaction.atomic
def create_project(*, actor, name: str, description: str = "") -> Project:
    project = Project.objects.create(name=name, description=description)
    ProjectMembership.objects.create(
        project=project,
        user=actor,
        role=ProjectMembership.Role.OWNER,
    )
    return project


def _locked_project(project_id: int) -> Project:
    return Project.objects.select_for_update().get(pk=project_id)


def _assert_actor_is_owner(*, project: Project, actor) -> None:
    if not ProjectMembership.objects.filter(
        project=project,
        user=actor,
        role=ProjectMembership.Role.OWNER,
    ).exists():
        raise ProjectMembershipError("Only project owners can manage memberships.")


def _assert_owner_remains(*, project: Project, membership: ProjectMembership) -> None:
    if membership.role != ProjectMembership.Role.OWNER:
        return
    if not ProjectMembership.objects.filter(
        project=project,
        role=ProjectMembership.Role.OWNER,
    ).exclude(pk=membership.pk).exists():
        raise ProjectMembershipError("A project must always have at least one owner.")


@transaction.atomic
def add_membership(*, project_id: int, actor, user_id: int, role: str) -> ProjectMembership:
    project = _locked_project(project_id)
    _assert_actor_is_owner(project=project, actor=actor)
    user = get_user_model().objects.get(pk=user_id)
    return ProjectMembership.objects.create(project=project, user=user, role=role)


@transaction.atomic
def change_membership_role(*, membership_id: int, actor, role: str) -> ProjectMembership:
    membership = ProjectMembership.objects.select_related("project").get(pk=membership_id)
    project = _locked_project(membership.project_id)
    membership = ProjectMembership.objects.select_for_update().get(pk=membership_id)
    _assert_actor_is_owner(project=project, actor=actor)

    if membership.role == ProjectMembership.Role.OWNER and role != ProjectMembership.Role.OWNER:
        _assert_owner_remains(project=project, membership=membership)

    membership.role = role
    membership.save(update_fields=["role"])
    return membership


@transaction.atomic
def remove_membership(*, membership_id: int, actor) -> None:
    membership = ProjectMembership.objects.select_related("project").get(pk=membership_id)
    project = _locked_project(membership.project_id)
    membership = ProjectMembership.objects.select_for_update().get(pk=membership_id)
    _assert_actor_is_owner(project=project, actor=actor)
    _assert_owner_remains(project=project, membership=membership)
    membership.delete()
