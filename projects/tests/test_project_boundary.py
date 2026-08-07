from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from projects.models import Project, ProjectMembership
from projects.services import create_project


class ProjectBoundaryApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="owner", password="pw")
        self.reviewer = user_model.objects.create_user(username="reviewer", password="pw")
        self.contributor = user_model.objects.create_user(username="contributor", password="pw")
        self.outsider = user_model.objects.create_user(username="outsider", password="pw")
        self.project = create_project(actor=self.owner, name="Alpha")
        self.owner_membership = self.project.memberships.get(user=self.owner)
        self.reviewer_membership = ProjectMembership.objects.create(
            project=self.project,
            user=self.reviewer,
            role=ProjectMembership.Role.REVIEWER,
        )
        self.contributor_membership = ProjectMembership.objects.create(
            project=self.project,
            user=self.contributor,
            role=ProjectMembership.Role.CONTRIBUTOR,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_project_creation_creates_owner_membership(self):
        creator = get_user_model().objects.create_user(username="creator", password="pw")
        self.authenticate(creator)

        response = self.client.post(reverse("project-list"), {"name": "Created"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(pk=response.data["id"])
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=project,
                user=creator,
                role=ProjectMembership.Role.OWNER,
            ).exists()
        )

    def test_outsider_cannot_access_project(self):
        self.authenticate(self.outsider)

        response = self.client.get(reverse("project-detail", args=[self.project.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_outsider_cannot_access_project_memberships(self):
        self.authenticate(self.outsider)

        response = self.client.get(
            reverse("project-membership-list", args=[self.project.id])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_members_can_read_project_and_memberships(self):
        self.authenticate(self.contributor)

        project_response = self.client.get(reverse("project-detail", args=[self.project.id]))
        memberships_response = self.client.get(
            reverse("project-membership-list", args=[self.project.id])
        )

        self.assertEqual(project_response.status_code, status.HTTP_200_OK)
        self.assertEqual(memberships_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(memberships_response.data), 3)

    def test_non_owner_cannot_manage_memberships(self):
        self.authenticate(self.reviewer)

        response = self.client.patch(
            reverse(
                "project-membership-detail",
                args=[self.project.id, self.contributor_membership.id],
            ),
            {"role": ProjectMembership.Role.REVIEWER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.contributor_membership.refresh_from_db()
        self.assertEqual(self.contributor_membership.role, ProjectMembership.Role.CONTRIBUTOR)

    def test_owner_can_add_and_change_membership(self):
        new_user = get_user_model().objects.create_user(username="new-member", password="pw")
        self.authenticate(self.owner)

        create_response = self.client.post(
            reverse("project-membership-list", args=[self.project.id]),
            {"user_id": new_user.id, "role": ProjectMembership.Role.CONTRIBUTOR},
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        membership_id = create_response.data["id"]
        update_response = self.client.patch(
            reverse("project-membership-detail", args=[self.project.id, membership_id]),
            {"role": ProjectMembership.Role.REVIEWER},
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            ProjectMembership.objects.get(pk=membership_id).role,
            ProjectMembership.Role.REVIEWER,
        )

    def test_last_owner_cannot_be_demoted(self):
        self.authenticate(self.owner)

        response = self.client.patch(
            reverse(
                "project-membership-detail",
                args=[self.project.id, self.owner_membership.id],
            ),
            {"role": ProjectMembership.Role.REVIEWER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.role, ProjectMembership.Role.OWNER)

    def test_last_owner_cannot_be_removed(self):
        self.authenticate(self.owner)

        response = self.client.delete(
            reverse(
                "project-membership-detail",
                args=[self.project.id, self.owner_membership.id],
            )
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(ProjectMembership.objects.filter(pk=self.owner_membership.id).exists())

    def test_owner_can_be_demoted_when_another_owner_exists(self):
        self.reviewer_membership.role = ProjectMembership.Role.OWNER
        self.reviewer_membership.save(update_fields=["role"])
        self.authenticate(self.owner)

        response = self.client.patch(
            reverse(
                "project-membership-detail",
                args=[self.project.id, self.owner_membership.id],
            ),
            {"role": ProjectMembership.Role.REVIEWER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.role, ProjectMembership.Role.REVIEWER)

    def test_duplicate_membership_rejected_by_database_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProjectMembership.objects.create(
                    project=self.project,
                    user=self.contributor,
                    role=ProjectMembership.Role.REVIEWER,
                )

    def test_non_owner_cannot_update_project_metadata(self):
        self.authenticate(self.reviewer)

        response = self.client.patch(
            reverse("project-detail", args=[self.project.id]),
            {"name": "Changed"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Alpha")
