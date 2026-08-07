from django.urls import path
from rest_framework.routers import SimpleRouter

from projects.views import ProjectMembershipViewSet, ProjectViewSet

router = SimpleRouter()
router.register("projects", ProjectViewSet, basename="project")

membership_list = ProjectMembershipViewSet.as_view({"get": "list", "post": "create"})
membership_detail = ProjectMembershipViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
)

urlpatterns = [
    *router.urls,
    path(
        "projects/<int:project_pk>/memberships/",
        membership_list,
        name="project-membership-list",
    ),
    path(
        "projects/<int:project_pk>/memberships/<int:pk>/",
        membership_detail,
        name="project-membership-detail",
    ),
]
