from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from . import views, qb_views

router = DefaultRouter()
router.register(r'companies', views.CompanyViewSet, basename='company')
router.register(r'projects', views.ProjectViewSet, basename='project')
router.register(r'team-members', views.TeamMemberViewSet, basename='team-member')
router.register(r'budgets', views.BudgetViewSet, basename='budget')
router.register(r'invoices', views.InvoiceViewSet, basename='invoice')
router.register(r'project-schedules', views.ProjectScheduleViewSet, basename='project-schedule')

# A1: multi-tenant foundation
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

urlpatterns = [
    path('', include(router.urls)),
    path('auth/token/', obtain_auth_token, name='api-token-auth'),

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
