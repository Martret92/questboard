from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from projects.models import Project, ProjectMembership
from quests.models import Quest, QuestDependency, QuestEvent


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


def _locked_project(project_id: int) -> Project:
    return Project.objects.select_for_update().get(pk=project_id)


def _record_event(*, quest: Quest, actor, event_type: str, data: dict | None = None) -> QuestEvent:
    return QuestEvent.objects.create(
        project_id=quest.project_id,
        quest=quest,
        quest_id_snapshot=quest.id,
        event_type=event_type,
        actor=actor,
        data=data or {},
    )


def _would_create_cycle(*, dependent_id: int, prerequisite_id: int) -> bool:
    stack = [prerequisite_id]
    visited = set()
    while stack:
        current = stack.pop()
        if current == dependent_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(
            QuestDependency.objects.filter(dependent_id=current).values_list("prerequisite_id", flat=True)
        )
    return False


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

    quest = Quest.objects.create(
        project_id=project_id,
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
        assignee=assignee,
    )
    _record_event(quest=quest, actor=actor, event_type=QuestEvent.Type.QUEST_CREATED)
    if assignee is not None:
        _record_event(
            quest=quest,
            actor=actor,
            event_type=QuestEvent.Type.ASSIGNEE_CHANGED,
            data={"from_membership_id": None, "to_membership_id": assignee.id},
        )
    return quest


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

    previous_assignee_id = quest.assignee_id
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

    if assignee_id is not ... and previous_assignee_id != quest.assignee_id:
        _record_event(
            quest=quest,
            actor=actor,
            event_type=QuestEvent.Type.ASSIGNEE_CHANGED,
            data={"from_membership_id": previous_assignee_id, "to_membership_id": quest.assignee_id},
        )
    return quest


@transaction.atomic
def add_dependency(*, dependent_id: int, prerequisite_id: int, actor) -> QuestDependency:
    dependent = Quest.objects.select_related("project").get(pk=dependent_id)
    _locked_project(dependent.project_id)
    actor_membership = _actor_membership(project_id=dependent.project_id, actor=actor)
    _require_planning_authority(actor_membership)

    dependent = Quest.objects.select_for_update().get(pk=dependent_id)
    if dependent.state != Quest.State.BACKLOG:
        raise QuestMutationError("Dependencies can only be changed while the dependent quest is BACKLOG.")
    if dependent_id == prerequisite_id:
        raise QuestMutationError("A quest cannot depend on itself.")

    try:
        prerequisite = Quest.objects.get(pk=prerequisite_id, project_id=dependent.project_id)
    except Quest.DoesNotExist as exc:
        raise QuestMutationError("Dependency quests must belong to the same project.") from exc

    if QuestDependency.objects.filter(dependent=dependent, prerequisite=prerequisite).exists():
        raise QuestMutationError("Dependency already exists.")
    if _would_create_cycle(dependent_id=dependent.id, prerequisite_id=prerequisite.id):
        raise QuestMutationError("Dependency would create a cycle.")

    try:
        edge = QuestDependency.objects.create(dependent=dependent, prerequisite=prerequisite)
    except IntegrityError as exc:
        raise QuestMutationError("Invalid dependency edge.") from exc

    _record_event(
        quest=dependent,
        actor=actor,
        event_type=QuestEvent.Type.DEPENDENCY_ADDED,
        data={"prerequisite_id": prerequisite.id},
    )
    return edge


@transaction.atomic
def remove_dependency(*, dependency_id: int, actor) -> None:
    edge = QuestDependency.objects.select_related("dependent").get(pk=dependency_id)
    _locked_project(edge.dependent.project_id)
    actor_membership = _actor_membership(project_id=edge.dependent.project_id, actor=actor)
    _require_planning_authority(actor_membership)

    edge = QuestDependency.objects.select_for_update().select_related("dependent").get(pk=dependency_id)
    if edge.dependent.state != Quest.State.BACKLOG:
        raise QuestMutationError("Dependencies can only be changed while the dependent quest is BACKLOG.")

    dependent = edge.dependent
    prerequisite_id = edge.prerequisite_id
    edge.delete()
    _record_event(
        quest=dependent,
        actor=actor,
        event_type=QuestEvent.Type.DEPENDENCY_REMOVED,
        data={"prerequisite_id": prerequisite_id},
    )


@transaction.atomic
def transition_quest(*, quest_id: int, actor, target_state: str) -> Quest:
    quest_snapshot = Quest.objects.only("id", "project_id", "state").get(pk=quest_id)

    if quest_snapshot.state == Quest.State.BACKLOG and target_state == Quest.State.READY:
        _locked_project(quest_snapshot.project_id)

    # Lock only the Quest row. Joining the nullable assignee relation here would
    # produce an outer join that PostgreSQL cannot lock with FOR UPDATE.
    quest = Quest.objects.select_for_update().get(pk=quest_id)
    actor_membership = _actor_membership(project_id=quest.project_id, actor=actor)
    source_state = quest.state

    if source_state == Quest.State.DONE:
        raise QuestMutationError("DONE is terminal.")

    if source_state == Quest.State.BACKLOG and target_state == Quest.State.READY:
        _require_planning_authority(actor_membership)
        blocked = QuestDependency.objects.filter(dependent=quest).exclude(
            prerequisite__state=Quest.State.DONE
        ).exists()
        if blocked:
            raise QuestMutationError("All prerequisites must be DONE before moving to READY.")
    elif source_state == Quest.State.READY and target_state == Quest.State.IN_PROGRESS:
        if quest.assignee_id is None:
            raise QuestMutationError("Quest must have an assignee before starting.")
        if quest.assignee.user_id != actor.id:
            raise QuestMutationError("Only the assignee can start this quest.")
    elif source_state == Quest.State.IN_PROGRESS and target_state == Quest.State.REVIEW:
        if quest.assignee_id is None or quest.assignee.user_id != actor.id:
            raise QuestMutationError("Only the assignee can submit this quest for review.")
    elif source_state == Quest.State.REVIEW and target_state == Quest.State.IN_PROGRESS:
        _require_planning_authority(actor_membership)
    elif source_state == Quest.State.REVIEW and target_state == Quest.State.DONE:
        _require_planning_authority(actor_membership)
        if quest.assignee_id is not None and quest.assignee.user_id == actor.id:
            raise QuestMutationError("Assignee cannot approve their own quest.")
    else:
        raise QuestMutationError(f"Invalid transition: {source_state} -> {target_state}.")

    quest.state = target_state
    quest.save(update_fields=["state", "updated_at"])
    _record_event(
        quest=quest,
        actor=actor,
        event_type=QuestEvent.Type.STATE_CHANGED,
        data={"from": source_state, "to": target_state},
    )
    return quest


@transaction.atomic
def delete_quest(*, quest_id: int, actor) -> None:
    quest = Quest.objects.select_for_update().get(pk=quest_id)
    actor_membership = _actor_membership(project_id=quest.project_id, actor=actor)
    _require_planning_authority(actor_membership)

    if quest.state != Quest.State.BACKLOG:
        raise QuestMutationError("Quest can only be deleted while BACKLOG.")
    if QuestDependency.objects.filter(prerequisite=quest).exists():
        raise QuestMutationError("Quest cannot be deleted while another quest depends on it.")

    quest.delete()
