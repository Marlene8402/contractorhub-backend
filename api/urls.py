from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from . import views, qb_views, auth_views, billing_views, webhook_views

router = DefaultRouter()
router.register(r'companies', views.CompanyViewSet, basename='company')
router.register(r'projects', views.ProjectViewSet, basename='project')
router.register(r'team-members', views.TeamMemberViewSet, basename='team-member')
router.register(r'budgets', views.BudgetViewSet, basename='budget')
router.register(r'invoices', views.InvoiceViewSet, basename='invoice')
router.register(r'project-schedules', views.ProjectScheduleViewSet, basename='project-schedule')

# A1: multi-tenant foundation
router.register(r'vendors', views.VendorViewSet, basename='vendor')
router.register(r'subcontracts', views.SubcontractViewSet, basename='subcontract')
router.register(r'subcontract-line-items', views.SubcontractLineItemViewSet, basename='subcontract-line-item')
router.register(r'sub-line-allocations', views.SubLineAllocationViewSet, basename='sub-line-allocation')
router.register(r'insurance-certificates', views.InsuranceCertificateViewSet, basename='insurance-certificate')
router.register(r'daily-logs', views.DailyLogViewSet, basename='daily-log')
router.register(r'lien-waivers', views.LienWaiverViewSet, basename='lien-waiver')

# A1.5: Change Orders + Pay Applications
router.register(r'prime-change-orders', views.PrimeChangeOrderViewSet, basename='prime-change-order')
router.register(r'sub-change-orders', views.SubcontractChangeOrderViewSet, basename='sub-change-order')
router.register(r'owner-contracts', views.OwnerContractViewSet, basename='owner-contract')
router.register(r'payment-applications', views.PaymentApplicationViewSet, basename='payment-application')
router.register(r'pay-app-lines', views.PayAppLineViewSet, basename='pay-app-line')

# A1.6: Tasks + Schedule + Phases + Budget lines + Allocations
router.register(r'project-phases',     views.ProjectPhaseViewSet,     basename='project-phase')
router.register(r'schedule-items',     views.ScheduleItemViewSet,     basename='schedule-item')
router.register(r'project-tasks',      views.ProjectTaskViewSet,      basename='project-task')
router.register(r'subtasks',           views.SubtaskViewSet,          basename='subtask')
router.register(r'task-comments',      views.TaskCommentViewSet,      basename='task-comment')
router.register(r'task-handoffs',      views.TaskHandoffViewSet,      basename='task-handoff')
router.register(r'task-watchers',      views.TaskWatcherViewSet,      basename='task-watcher')
router.register(r'task-templates',     views.TaskTemplateViewSet,     basename='task-template')
router.register(r'budget-line-items',  views.BudgetLineItemViewSet,   basename='budget-line-item')
router.register(r'budget-allocations', views.BudgetAllocationViewSet, basename='budget-allocation')

urlpatterns = [
    path('', include(router.urls)),

    # Auth: token issue (login), registration, identity
    path('auth/token/',    obtain_auth_token,   name='api-token-auth'),
    path('auth/register/', auth_views.register, name='auth_register'),
    path('auth/me/',       auth_views.me,       name='auth_me'),

    # Stripe billing
    path('billing/checkout/', billing_views.create_checkout_session, name='billing_checkout'),
    path('billing/portal/',   billing_views.create_portal_session,   name='billing_portal'),
    path('billing/status/',   billing_views.subscription_status,     name='billing_status'),
    path('webhooks/stripe/',  webhook_views.stripe_webhook,          name='stripe_webhook'),

    # QuickBooks OAuth
    path('auth/quickbooks/',          qb_views.quickbooks_auth,       name='qb_auth'),
    path('auth/quickbooks/callback/', qb_views.quickbooks_callback,   name='qb_callback'),
    path('qb/disconnect/',            qb_views.quickbooks_disconnect, name='qb_disconnect'),

    # QuickBooks sync
    path('qb/sync-status/',           qb_views.qb_sync_status,        name='qb_sync_status'),
    path('qb/sync-invoice/',          qb_views.qb_sync_invoice,       name='qb_sync_invoice'),

    # GL mappings
    path('qb/gl-mappings/',           qb_views.qb_gl_mappings,        name='qb_gl_mappings'),
    path('qb/gl-mappings/<int:mapping_id>/',
                                       qb_views.qb_gl_mapping_detail,  name='qb_gl_mapping_detail'),
]
