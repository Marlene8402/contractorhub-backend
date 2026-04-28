from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import redirect
from django.conf import settings
from datetime import datetime, timedelta
from .models import Company, TeamMember, Project, Budget, Invoice, ProjectSchedule, QBSyncLog
from .serializers import (
    CompanySerializer, TeamMemberSerializer, ProjectSerializer, ProjectListSerializer,
    BudgetSerializer, InvoiceSerializer, ProjectScheduleSerializer, QBSyncLogSerializer
)
# QB integration will be imported when needed
try:
    from .qb_integration import QBIntegration
except ImportError:
    QBIntegration = None


class CompanyViewSet(viewsets.ModelViewSet):
    """Manage company profile and QB connection"""
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Company.objects.filter(owner=self.request.user)
    
    @action(detail=True, methods=['get'])
    def qb_auth_url(self, request, pk=None):
        """Get QB OAuth URL"""
        company = self.get_object()
        qb = QBIntegration(company)
        auth_url = qb.get_auth_url()
        return Response({'auth_url': auth_url})
    
    @action(detail=True, methods=['post'])
    def disconnect_qb(self, request, pk=None):
        """Disconnect QB account"""
        company = self.get_object()
        company.qb_connected = False
        company.qb_access_token = None
        company.qb_refresh_token = None
        company.save()
        return Response({'status': 'QB disconnected'})


class TeamMemberViewSet(viewsets.ModelViewSet):
    """Manage team members"""
    serializer_class = TeamMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            company = Company.objects.get(owner=self.request.user)
            return TeamMember.objects.filter(company=company)
        except Company.DoesNotExist:
            return TeamMember.objects.none()

    def perform_create(self, serializer):
        company = Company.objects.get(owner=self.request.user)
        serializer.save(company=company)


class BudgetViewSet(viewsets.ModelViewSet):
    """Manage project budgets"""
    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            company = Company.objects.get(owner=self.request.user)
            return Budget.objects.filter(project__company=company)
        except Company.DoesNotExist:
            return Budget.objects.none()
    
    @action(detail=True, methods=['post'])
    def sync_to_qb(self, request, pk=None):
        """Sync budget to QB"""
        budget = self.get_object()
        company = Company.objects.get(owner=self.request.user)
        qb = QBIntegration(company)
        
        try:
            success = qb.create_customer(budget.project)
            return Response({'status': 'success', 'qb_id': success})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InvoiceViewSet(viewsets.ModelViewSet):
    """Manage invoices"""
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        try:
            company = Company.objects.get(owner=self.request.user)
            return Invoice.objects.filter(project__company=company)
        except Company.DoesNotExist:
            return Invoice.objects.none()
    
    def perform_create(self, serializer):
        # Auto-generate invoice number
        company = Company.objects.get(owner=self.request.user)
        last_invoice = Invoice.objects.filter(project__company=company).order_by('-id').first()
        invoice_num = (int(last_invoice.invoice_number.split('-')[1]) + 1 
                      if last_invoice else 1)
        invoice_number = f"INV-{invoice_num:04d}"
        serializer.save(invoice_number=invoice_number)
    
    @action(detail=True, methods=['post'])
    def sync_to_qb(self, request, pk=None):
        """Push invoice to QB"""
        invoice = self.get_object()
        company = Company.objects.get(owner=self.request.user)
        qb = QBIntegration(company)
        
        try:
            success = qb.create_invoice(invoice)
            return Response({'status': 'success' if success else 'error'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def sync_from_qb(self, request):
        """Pull invoices from QB"""
        company = Company.objects.get(owner=self.request.user)
        qb = QBIntegration(company)
        
        try:
            count = qb.sync_invoices_from_qb()
            return Response({'status': 'success', 'invoices_synced': count})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ProjectViewSet(viewsets.ModelViewSet):
    """Manage construction projects"""
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        try:
            company = Company.objects.get(owner=self.request.user)
            return Project.objects.filter(company=company)
        except Company.DoesNotExist:
            return Project.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ProjectListSerializer
        return ProjectSerializer
    
    def perform_create(self, serializer):
        company = Company.objects.get(owner=self.request.user)
        project = serializer.save(company=company)
        
        # Auto-create budget and schedule
        Budget.objects.create(project=project)
        ProjectSchedule.objects.create(
            project=project,
            planned_start=project.start_date,
            planned_end=project.end_date
        )
    
    @action(detail=True, methods=['post'])
    def update_schedule(self, request, pk=None):
        """Update project schedule"""
        project = self.get_object()
        schedule_data = request.data
        
        schedule = project.schedule
        schedule.percent_complete = schedule_data.get('percent_complete', schedule.percent_complete)
        schedule.actual_start = schedule_data.get('actual_start', schedule.actual_start)
        schedule.actual_end = schedule_data.get('actual_end', schedule.actual_end)
        schedule.notes = schedule_data.get('notes', schedule.notes)
        schedule.save()
        
        return Response(ProjectScheduleSerializer(schedule).data)
    
    @action(detail=True, methods=['post'])
    def update_budget(self, request, pk=None):
        """Update project budget"""
        project = self.get_object()
        budget_data = request.data
        
        budget = project.budget
        budget.estimated_labor = budget_data.get('estimated_labor', budget.estimated_labor)
        budget.estimated_materials = budget_data.get('estimated_materials', budget.estimated_materials)
        budget.estimated_equipment = budget_data.get('estimated_equipment', budget.estimated_equipment)
        budget.estimated_overhead = budget_data.get('estimated_overhead', budget.estimated_overhead)
        budget.estimated_profit = budget_data.get('estimated_profit', budget.estimated_profit)
        
        budget.actual_labor = budget_data.get('actual_labor', budget.actual_labor)
        budget.actual_materials = budget_data.get('actual_materials', budget.actual_materials)
        budget.actual_equipment = budget_data.get('actual_equipment', budget.actual_equipment)
        budget.actual_overhead = budget_data.get('actual_overhead', budget.actual_overhead)
        
        budget.notes = budget_data.get('notes', budget.notes)
        budget.save()
        
        return Response(BudgetSerializer(budget).data)
    
    @action(detail=False, methods=['get'])
    def active_projects(self, request):
        """Get active projects only"""
        company = Company.objects.get(owner=self.request.user)
        projects = Project.objects.filter(company=company, status__in=['active', 'awarded'])
        serializer = self.get_serializer(projects, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get project summary dashboard"""
        company = Company.objects.get(owner=self.request.user)
        projects = Project.objects.filter(company=company)
        
        total_value = sum(p.contract_amount for p in projects)
        active_count = projects.filter(status__in=['active', 'awarded']).count()
        completed_count = projects.filter(status='completed').count()
        
        return Response({
            'total_projects': projects.count(),
            'total_contract_value': float(total_value),
            'active_projects': active_count,
            'completed_projects': completed_count
        })


class ProjectScheduleViewSet(viewsets.ModelViewSet):
    """Manage project schedules"""
    serializer_class = ProjectScheduleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            company = Company.objects.get(owner=self.request.user)
            return ProjectSchedule.objects.filter(project__company=company)
        except Company.DoesNotExist:
            return ProjectSchedule.objects.none()


class QBSyncLogViewSet(viewsets.ReadOnlyModelViewSet):
    """View QB sync operation logs"""
    serializer_class = QBSyncLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            company = Company.objects.get(owner=self.request.user)
            return QBSyncLog.objects.filter(company=company)
        except Company.DoesNotExist:
            return QBSyncLog.objects.none()


def qb_callback(request):
    """QB OAuth callback endpoint"""
    auth_code = request.GET.get('code')
    realm_id = request.GET.get('realmId')
    
    if not auth_code:
        return redirect(f'{settings.FRONTEND_URL}/settings/qb?error=no_auth_code')
    
    try:
        company = Company.objects.get(owner=request.user)
        company.qb_realm_id = realm_id
        company.save()
        
        qb = QBIntegration(company)
        if qb.get_access_token(auth_code):
            return redirect(f'{settings.FRONTEND_URL}/settings/qb?success=true')
        else:
            return redirect(f'{settings.FRONTEND_URL}/settings/qb?error=token_exchange_failed')
    except Exception as e:
        return redirect(f'{settings.FRONTEND_URL}/settings/qb?error={str(e)}')
