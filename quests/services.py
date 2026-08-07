from django.core.exceptions import ValidationError
from django.db import transaction

from projects.models import ProjectMembership
from quests.models import Quest


class QuestMutationError(ValidationError):
    pass


def _actor_membership(*, project_id: int, actor) -> ProjectMembership:
    try:
        return ProjectMembership.objects.get(project_id=project_id, user=actor)
    except ProjectMembership.DoesNotExist as exc:
        raise QuestMutationError("Actor is not a member of this project.") from exc


def _require_planning_authority(membership: ProjectMembership) -> None:
    if membership.role not in {ProjectMembership.Role.OWNER, ProjectMembership.Role.REVIEWER}:
        raise QuestMutationError("Only owners or reviewers can perform this operation.")


@transaction.atomic
def create_quest(*, project_id: int, actor, title: str, description: str = "", priority: str = Quest.Priority.MEDIUM, due_date=None, assignee_id: int | None = None) -> Quest:
    actor_membership = _actor_membership(project_id=project_id, actor=actor)

    assignee = None
    if assignee_id is not None:
        _require_planning_authority(actor_membership)
        try:
            assignee = ProjectMembership.objects.get(pk=assignee_id, project_id=project_id)
        except ProjectMembership.DoesNotExist as exc:
            raise QuestMutationError("Assignee must belong to the same project.") from exc

    return Quest.objects.create(
        project_id=project_id,
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
        assignee=assignee,
    )


@transaction.atomic
def update_quest(
    *,
    quest_id: int,
    actor,
    title=...,
    description=...,
    priority=...,
    due_date=...,
    assignee_id=...,
) -> Quest:
    quest = Quest.objects.select_for_update().get(pk=quest_id)
    actor_membership = _actor_membership(project_id=quest.project_id, actor=actor)

    metadata_requested = any(value is not ... for value in (title, description, priority, due_date))
    if metadata_requested and quest.state != Quest.State.BACKLOG:
        raise QuestMutationError("Quest metadata can only be edited while the quest is BACKLOG.")

    if assignee_id is not ...:
        _require_planning_authority(actor_membership)
        if quest.state not in {Quest.State.BACKLOG, Quest.State.READY}:
            raise QuestMutationError("Assignee can only be changed while the quest is BACKLOG or READY.")

        assignee = None
        if assignee_id is not None:
            try:
                assignee = ProjectMembership.objects.get(pk=assignee_id, project_id=quest.project_id)
            except ProjectMembership.DoesNotExist as exc:
                raise QuestMutationError("Assignee must belong to the same project.") from exc
        quest.assignee = assignee

    update_fields = []
    for field_name, value in (
        ("title", title),
        ("description", description),
        ("priority", priority),
        ("due_date", due_date),
    ):
        if value is not ...:
            setattr(quest, field_name, value)
            update_fields.append(field_name)

    if assignee_id is not ...:
        update_fields.append("assignee")

    if update_fields:
        update_fields.append("updated_at")
        quest.save(update_fields=update_fields)
    return quest


@transaction.atomic
def delete_quest(*, quest_id: int, actor) -> None:
    quest = Quest.objects.select_for_update().get(pk=quest_id)
    actor_membership = _actor_membership(project_id=quest.project_id, actor=actor)
    _require_planning_authority(actor_membership)

    if quest.state != Quest.State.BACKLOG:
        raise QuestMutationError("Quest can only be deleted while BACKLOG.")

    quest.delete()
