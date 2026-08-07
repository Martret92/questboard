from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from projects.models import ProjectMembership
from projects.services import add_membership, create_project
from quests.models import Quest, QuestDependency, QuestEvent
from quests.services import create_quest


User = get_user_model()


class WorkflowDependencyAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner-m3", password="pass")
        self.reviewer = User.objects.create_user(username="reviewer-m3", password="pass")
        self.contributor = User.objects.create_user(username="contributor-m3", password="pass")
        self.other = User.objects.create_user(username="other-m3", password="pass")

        self.project = create_project(actor=self.owner, name="M3")
        self.owner_membership = ProjectMembership.objects.get(project=self.project, user=self.owner)
        self.reviewer_membership = add_membership(
            project_id=self.project.id,
            actor=self.owner,
            user_id=self.reviewer.id,
            role=ProjectMembership.Role.REVIEWER,
        )
        self.contributor_membership = add_membership(
            project_id=self.project.id,
            actor=self.owner,
            user_id=self.contributor.id,
            role=ProjectMembership.Role.CONTRIBUTOR,
        )
        self.other_project = create_project(actor=self.other, name="Other M3")
        self.other_membership = ProjectMembership.objects.get(project=self.other_project, user=self.other)

    def dependency_url(self, quest):
        return reverse(
            "project-quest-dependency-list",
            kwargs={"project_pk": self.project.id, "quest_pk": quest.id},
        )

    def dependency_detail_url(self, quest, edge):
        return reverse(
            "project-quest-dependency-detail",
            kwargs={"project_pk": self.project.id, "quest_pk": quest.id, "pk": edge.id},
        )

    def transition_url(self, quest):
        return reverse(
            "project-quest-transition",
            kwargs={"project_pk": self.project.id, "quest_pk": quest.id},
        )

    def event_url(self, quest_id):
        return reverse(
            "project-quest-event-list",
            kwargs={"project_pk": self.project.id, "quest_pk": quest_id},
        )

    def add_dependency(self, dependent, prerequisite, actor=None):
        self.client.force_authenticate(actor or self.owner)
        return self.client.post(
            self.dependency_url(dependent),
            {"prerequisite_id": prerequisite.id},
            format="json",
        )

    def transition(self, quest, actor, target):
        self.client.force_authenticate(actor)
        return self.client.post(
            self.transition_url(quest),
            {"target_state": target},
            format="json",
        )

    def test_dependency_rejects_self_cross_project_duplicate_and_cycle(self):
        a = Quest.objects.create(project=self.project, title="A")
        b = Quest.objects.create(project=self.project, title="B")
        c = Quest.objects.create(project=self.project, title="C")
        foreign = Quest.objects.create(project=self.other_project, title="Foreign")

        self.assertEqual(self.add_dependency(a, a).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.add_dependency(a, foreign).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.add_dependency(a, b).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.add_dependency(a, b).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.add_dependency(b, c).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.add_dependency(c, a).status_code, status.HTTP_400_BAD_REQUEST)

    def test_contributor_cannot_manage_dependencies(self):
        dependent = Quest.objects.create(project=self.project, title="Dependent")
        prerequisite = Quest.objects.create(project=self.project, title="Prerequisite")
        response = self.add_dependency(dependent, prerequisite, actor=self.contributor)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dependency_graph_is_frozen_after_dependent_leaves_backlog(self):
        dependent = Quest.objects.create(project=self.project, title="Dependent", state=Quest.State.READY)
        prerequisite = Quest.objects.create(project=self.project, title="Prerequisite")
        self.assertEqual(self.add_dependency(dependent, prerequisite).status_code, status.HTTP_400_BAD_REQUEST)

        dependent.state = Quest.State.BACKLOG
        dependent.save(update_fields=["state"])
        response = self.add_dependency(dependent, prerequisite)
        edge = QuestDependency.objects.get(pk=response.data["id"])
        dependent.state = Quest.State.READY
        dependent.save(update_fields=["state"])

        self.client.force_authenticate(self.owner)
        self.assertEqual(
            self.client.delete(self.dependency_detail_url(dependent, edge)).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_backlog_to_ready_requires_all_prerequisites_done(self):
        prerequisite = Quest.objects.create(project=self.project, title="Prerequisite")
        dependent = Quest.objects.create(project=self.project, title="Dependent")
        self.assertEqual(self.add_dependency(dependent, prerequisite).status_code, status.HTTP_201_CREATED)

        response = self.transition(dependent, self.owner, Quest.State.READY)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        prerequisite.state = Quest.State.DONE
        prerequisite.save(update_fields=["state"])
        response = self.transition(dependent, self.reviewer, Quest.State.READY)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dependent.refresh_from_db()
        self.assertEqual(dependent.state, Quest.State.READY)

    def test_completing_prerequisite_does_not_auto_transition_dependent(self):
        prerequisite = Quest.objects.create(project=self.project, title="Prerequisite", state=Quest.State.DONE)
        dependent = Quest.objects.create(project=self.project, title="Dependent")
        QuestDependency.objects.create(dependent=dependent, prerequisite=prerequisite)
        dependent.refresh_from_db()
        self.assertEqual(dependent.state, Quest.State.BACKLOG)

    def test_ready_to_in_progress_requires_assignee_and_actor_is_assignee(self):
        quest = Quest.objects.create(project=self.project, title="Run", state=Quest.State.READY)
        self.assertEqual(
            self.transition(quest, self.contributor, Quest.State.IN_PROGRESS).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        quest.assignee = self.contributor_membership
        quest.save(update_fields=["assignee"])
        self.assertEqual(
            self.transition(quest, self.reviewer, Quest.State.IN_PROGRESS).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.transition(quest, self.contributor, Quest.State.IN_PROGRESS).status_code,
            status.HTTP_200_OK,
        )

    def test_in_progress_to_review_requires_assignee(self):
        quest = Quest.objects.create(
            project=self.project,
            title="Submit",
            state=Quest.State.IN_PROGRESS,
            assignee=self.contributor_membership,
        )
        self.assertEqual(
            self.transition(quest, self.reviewer, Quest.State.REVIEW).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.transition(quest, self.contributor, Quest.State.REVIEW).status_code,
            status.HTTP_200_OK,
        )

    def test_review_to_in_progress_requires_review_authority(self):
        quest = Quest.objects.create(
            project=self.project,
            title="Changes",
            state=Quest.State.REVIEW,
            assignee=self.contributor_membership,
        )
        self.assertEqual(
            self.transition(quest, self.contributor, Quest.State.IN_PROGRESS).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.transition(quest, self.reviewer, Quest.State.IN_PROGRESS).status_code,
            status.HTTP_200_OK,
        )

    def test_review_to_done_forbids_self_approval_even_for_owner(self):
        quest = Quest.objects.create(
            project=self.project,
            title="Owner work",
            state=Quest.State.REVIEW,
            assignee=self.owner_membership,
        )
        self.assertEqual(
            self.transition(quest, self.owner, Quest.State.DONE).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.transition(quest, self.reviewer, Quest.State.DONE).status_code,
            status.HTTP_200_OK,
        )

    def test_done_is_terminal_and_shortcuts_are_rejected(self):
        done = Quest.objects.create(project=self.project, title="Done", state=Quest.State.DONE)
        backlog = Quest.objects.create(project=self.project, title="Backlog")
        self.assertEqual(
            self.transition(done, self.owner, Quest.State.REVIEW).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.transition(backlog, self.owner, Quest.State.DONE).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_state_change_creates_audit_event(self):
        quest = Quest.objects.create(project=self.project, title="Audit")
        response = self.transition(quest, self.owner, Quest.State.READY)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event = QuestEvent.objects.get(quest=quest, event_type=QuestEvent.Type.STATE_CHANGED)
        self.assertEqual(event.actor, self.owner)
        self.assertEqual(event.data, {"from": Quest.State.BACKLOG, "to": Quest.State.READY})

    def test_create_assignment_and_dependency_operations_create_events(self):
        quest = create_quest(
            project_id=self.project.id,
            actor=self.owner,
            title="Audited create",
            assignee_id=self.contributor_membership.id,
        )
        prerequisite = Quest.objects.create(project=self.project, title="Prerequisite")
        self.assertEqual(self.add_dependency(quest, prerequisite).status_code, status.HTTP_201_CREATED)

        types = list(QuestEvent.objects.filter(quest=quest).values_list("event_type", flat=True))
        self.assertIn(QuestEvent.Type.QUEST_CREATED, types)
        self.assertIn(QuestEvent.Type.ASSIGNEE_CHANGED, types)
        self.assertIn(QuestEvent.Type.DEPENDENCY_ADDED, types)

    def test_quest_delete_rejected_if_another_quest_depends_on_it(self):
        prerequisite = Quest.objects.create(project=self.project, title="Cannot delete")
        dependent = Quest.objects.create(project=self.project, title="Depends")
        QuestDependency.objects.create(dependent=dependent, prerequisite=prerequisite)
        self.client.force_authenticate(self.owner)
        url = reverse("project-quest-detail", kwargs={"project_pk": self.project.id, "pk": prerequisite.id})
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Quest.objects.filter(pk=prerequisite.id).exists())

    def test_audit_events_survive_legal_quest_deletion(self):
        quest = create_quest(project_id=self.project.id, actor=self.owner, title="Delete audited")
        quest_id = quest.id
        self.client.force_authenticate(self.owner)
        detail_url = reverse("project-quest-detail", kwargs={"project_pk": self.project.id, "pk": quest_id})
        self.assertEqual(self.client.delete(detail_url).status_code, status.HTTP_204_NO_CONTENT)

        event = QuestEvent.objects.get(quest_id_snapshot=quest_id, event_type=QuestEvent.Type.QUEST_CREATED)
        self.assertIsNone(event.quest_id)
        response = self.client.get(self.event_url(quest_id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["quest_id_snapshot"], quest_id)

    def test_nonmember_cannot_read_dependencies_or_events(self):
        quest = create_quest(project_id=self.project.id, actor=self.owner, title="Private")
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.dependency_url(quest)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(self.event_url(quest.id)).status_code, status.HTTP_404_NOT_FOUND)
