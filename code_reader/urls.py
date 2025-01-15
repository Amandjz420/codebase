from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import (ProjectViewSet, FileViewSet, login_view,
                    DocumentDetailFetch, ExecutorView,
                    ProjectDetailViewSet, ProjectListViewSet, QnAView,
                    ProjectFilesView, UserDetailView)
from conversation.views import MessagesDetailViewSet

router = DefaultRouter()
router.register(r'projects', ProjectViewSet)
router.register(r'files', FileViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('login/', login_view, name='login'),
    path('document_detail_fetch/', DocumentDetailFetch.as_view(), name='document_detail_fetch'),
    path('projects/<int:pk>/', ProjectDetailViewSet.as_view(), name='project_detail'),
    path('projects/<int:project_id>/conversation/<str:conversation_id>/get_your_answer/', QnAView.as_view(), name='new_query_view'),
    path('projects/<int:project_id>/conversation/<str:conversation_id>/executor/', ExecutorView.as_view(), name='executor_view'),
    path('conversation/<str:conversation_id>/', MessagesDetailViewSet.as_view(), name='get_messages'),
    path('projects/<int:project_id>/files/', ProjectFilesView.as_view(), name='project_files'),
    path('user/details/', UserDetailView.as_view(), name='user-details')
]