from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Company, TeamMember, Project, Budget, Invoice, ProjectSchedule
from .serializers import (
    CompanySerializer, TeamMemberSerializer, ProjectSerializer, ProjectListSerializer,
    BudgetSerializer, InvoiceSerializer, ProjectScheduleSerializer
)


class CompanyViewSet(viewsets.ModelViewSet):
    """Manage company profile"""
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Company.objects.filter(owner=self.request.user)


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


