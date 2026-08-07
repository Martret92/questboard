from django.urls import path

from quests.views import QuestDependencyViewSet, QuestEventView, QuestTransitionView, QuestViewSet

quest_list = QuestViewSet.as_view({"get": "list", "post": "create"})
quest_detail = QuestViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
dependency_list = QuestDependencyViewSet.as_view({"get": "list", "post": "create"})
dependency_detail = QuestDependencyViewSet.as_view({"delete": "destroy"})
transition = QuestTransitionView.as_view({"post": "create"})
event_list = QuestEventView.as_view({"get": "list"})

urlpatterns = [
    path("projects/<int:project_pk>/quests/", quest_list, name="project-quest-list"),
    path("projects/<int:project_pk>/quests/<int:pk>/", quest_detail, name="project-quest-detail"),
    path(
        "projects/<int:project_pk>/quests/<int:quest_pk>/dependencies/",
        dependency_list,
        name="project-quest-dependency-list",
    ),
    path(
        "projects/<int:project_pk>/quests/<int:quest_pk>/dependencies/<int:pk>/",
        dependency_detail,
        name="project-quest-dependency-detail",
    ),
    path(
        "projects/<int:project_pk>/quests/<int:quest_pk>/transition/",
        transition,
        name="project-quest-transition",
    ),
    path(
        "projects/<int:project_pk>/quests/<int:quest_pk>/events/",
        event_list,
        name="project-quest-event-list",
    ),
]
