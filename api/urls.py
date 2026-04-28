from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from . import views

router = DefaultRouter()
router.register(r'companies', views.CompanyViewSet, basename='company')
router.register(r'projects', views.ProjectViewSet, basename='project')
router.register(r'team-members', views.TeamMemberViewSet, basename='team-member')
router.register(r'budgets', views.BudgetViewSet, basename='budget')
router.register(r'invoices', views.InvoiceViewSet, basename='invoice')
router.register(r'project-schedules', views.ProjectScheduleViewSet, basename='project-schedule')
router.register(r'qb-sync-logs', views.QBSyncLogViewSet, basename='qb-sync-log')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/token/', obtain_auth_token, name='api-token-auth'),
    path('qb/callback/', views.qb_callback, name='qb-callback'),
]
