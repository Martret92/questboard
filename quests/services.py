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
def update_quest_metadata(*, quest_id: int, actor, title: str | None = None, description: str | None = None, priority: str | None = None, due_date=...) -> Quest:
    quest = Quest.objects.select_for_update().select_related("project").get(pk=quest_id)
    _actor_membership(project_id=quest.project_id, actor=actor)

    if quest.state != Quest.State.BACKLOG:
        raise QuestMutationError("Quest metadata can only be edited while the quest is BACKLOG.")

    update_fields = []
    if title is not None:
        quest.title = title
        update_fields.append("title")
    if description is not None:
        quest.description = description
        update_fields.append("description")
    if priority is not None:
        quest.priority = priority
        update_fields.append("priority")
    if due_date is not ...:
        quest.due_date = due_date
        update_fields.append("due_date")

    if update_fields:
        update_fields.append("updated_at")
        quest.save(update_fields=update_fields)
    return quest


@transaction.atomic
def assign_quest(*, quest_id: int, actor, assignee_id: int | None) -> Quest:
    quest = Quest.objects.select_for_update().get(pk=quest_id)
    actor_membership = _actor_membership(project_id=quest.project_id, actor=actor)
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
    quest.save(update_fields=["assignee", "updated_at"])
    return quest


@transaction.atomic
def delete_quest(*, quest_id: int, actor) -> None:
    quest = Quest.objects.select_for_update().get(pk=quest_id)
    actor_membership = _actor_membership(project_id=quest.project_id, actor=actor)
    _require_planning_authority(actor_membership)

    if quest.state != Quest.State.BACKLOG:
        raise QuestMutationError("Quest can only be deleted while BACKLOG.")

    quest.delete()
