from django.urls import path

from quests.views import QuestViewSet

quest_list = QuestViewSet.as_view({"get": "list", "post": "create"})
quest_detail = QuestViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})

urlpatterns = [
    path("projects/<int:project_pk>/quests/", quest_list, name="project-quest-list"),
    path("projects/<int:project_pk>/quests/<int:pk>/", quest_detail, name="project-quest-detail"),
]
