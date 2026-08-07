from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from projects.models import ProjectMembership
from projects.services import add_membership, create_project
from quests.models import Quest


User = get_user_model()


class QuestCoreAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pass")
        self.reviewer = User.objects.create_user(username="reviewer", password="pass")
        self.contributor = User.objects.create_user(username="contributor", password="pass")
        self.outsider = User.objects.create_user(username="outsider", password="pass")

        self.project = create_project(actor=self.owner, name="Alpha")
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

        self.other_owner = User.objects.create_user(username="other-owner", password="pass")
        self.other_project = create_project(actor=self.other_owner, name="Other")
        self.other_membership = ProjectMembership.objects.get(project=self.other_project, user=self.other_owner)

    def list_url(self, project=None):
        project = project or self.project
        return reverse("project-quest-list", kwargs={"project_pk": project.id})

    def detail_url(self, quest):
        return reverse("project-quest-detail", kwargs={"project_pk": quest.project_id, "pk": quest.id})

    def membership_detail_url(self, membership):
        return reverse(
            "project-membership-detail",
            kwargs={"project_pk": membership.project_id, "pk": membership.id},
        )

    def test_member_can_create_unassigned_quest_in_backlog(self):
        self.client.force_authenticate(self.contributor)
        response = self.client.post(
            self.list_url(),
            {"title": "Implement endpoint", "priority": Quest.Priority.HIGH, "due_date": "2026-08-20"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        quest = Quest.objects.get(pk=response.data["id"])
        self.assertEqual(quest.project, self.project)
        self.assertEqual(quest.state, Quest.State.BACKLOG)
        self.assertIsNone(quest.assignee)

    def test_nonmember_cannot_list_or_create_project_quests(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.list_url()).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.post(self.list_url(), {"title": "Hidden"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_nonmember_cannot_retrieve_existing_quest(self):
        quest = Quest.objects.create(project=self.project, title="Secret")
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.detail_url(quest)).status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_assign_same_project_membership_on_create(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            self.list_url(),
            {"title": "Assigned", "assignee_id": self.contributor_membership.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Quest.objects.get(pk=response.data["id"]).assignee, self.contributor_membership)

    def test_cross_project_assignee_is_rejected(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            self.list_url(),
            {"title": "Bad assignment", "assignee_id": self.other_membership.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Quest.objects.filter(title="Bad assignment").exists())

    def test_contributor_cannot_assign(self):
        quest = Quest.objects.create(project=self.project, title="Plan")
        self.client.force_authenticate(self.contributor)
        response = self.client.patch(
            self.detail_url(quest),
            {"assignee_id": self.contributor_membership.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        quest.refresh_from_db()
        self.assertIsNone(quest.assignee)

    def test_member_can_edit_backlog_metadata(self):
        quest = Quest.objects.create(project=self.project, title="Old")
        self.client.force_authenticate(self.contributor)
        response = self.client.patch(
            self.detail_url(quest),
            {"title": "New", "priority": Quest.Priority.HIGH},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        quest.refresh_from_db()
        self.assertEqual(quest.title, "New")
        self.assertEqual(quest.priority, Quest.Priority.HIGH)

    def test_metadata_edit_rejected_after_backlog(self):
        quest = Quest.objects.create(project=self.project, title="Frozen", state=Quest.State.READY)
        self.client.force_authenticate(self.contributor)
        response = self.client.patch(self.detail_url(quest), {"title": "Changed"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        quest.refresh_from_db()
        self.assertEqual(quest.title, "Frozen")

    def test_assignment_mutable_in_ready(self):
        quest = Quest.objects.create(project=self.project, title="Ready", state=Quest.State.READY)
        self.client.force_authenticate(self.reviewer)
        response = self.client.patch(
            self.detail_url(quest),
            {"assignee_id": self.contributor_membership.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        quest.refresh_from_db()
        self.assertEqual(quest.assignee, self.contributor_membership)

    def test_assignment_frozen_from_in_progress(self):
        quest = Quest.objects.create(
            project=self.project,
            title="Executing",
            state=Quest.State.IN_PROGRESS,
            assignee=self.contributor_membership,
        )
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            self.detail_url(quest),
            {"assignee_id": self.reviewer_membership.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        quest.refresh_from_db()
        self.assertEqual(quest.assignee, self.contributor_membership)

    def test_assigned_membership_cannot_be_deleted(self):
        Quest.objects.create(
            project=self.project,
            title="Protected assignment",
            assignee=self.contributor_membership,
        )
        self.client.force_authenticate(self.owner)

        response = self.client.delete(self.membership_detail_url(self.contributor_membership))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(ProjectMembership.objects.filter(pk=self.contributor_membership.id).exists())

    def test_state_cannot_be_changed_by_generic_patch(self):
        quest = Quest.objects.create(project=self.project, title="No shortcut")
        self.client.force_authenticate(self.owner)
        response = self.client.patch(self.detail_url(quest), {"state": Quest.State.DONE}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        quest.refresh_from_db()
        self.assertEqual(quest.state, Quest.State.BACKLOG)

    def test_only_planning_authority_can_delete_backlog_quest(self):
        quest = Quest.objects.create(project=self.project, title="Delete me")
        self.client.force_authenticate(self.contributor)
        self.assertEqual(self.client.delete(self.detail_url(quest)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Quest.objects.filter(pk=quest.id).exists())

        self.client.force_authenticate(self.reviewer)
        self.assertEqual(self.client.delete(self.detail_url(quest)).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Quest.objects.filter(pk=quest.id).exists())

    def test_non_backlog_quest_cannot_be_deleted(self):
        quest = Quest.objects.create(project=self.project, title="Keep", state=Quest.State.READY)
        self.client.force_authenticate(self.owner)
        response = self.client.delete(self.detail_url(quest))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Quest.objects.filter(pk=quest.id).exists())

    def test_list_filters_by_state_priority_and_assignee(self):
        Quest.objects.create(
            project=self.project,
            title="Match",
            state=Quest.State.READY,
            priority=Quest.Priority.HIGH,
            assignee=self.contributor_membership,
        )
        Quest.objects.create(project=self.project, title="Other", priority=Quest.Priority.LOW)

        self.client.force_authenticate(self.owner)
        response = self.client.get(
            self.list_url(),
            {"state": Quest.State.READY, "priority": Quest.Priority.HIGH, "assignee": self.contributor_membership.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["title"] for item in response.data], ["Match"])
