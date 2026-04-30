from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import (
    Company, TeamMember, Project, Budget, Invoice, ProjectSchedule,
    Subcontract, SubcontractLineItem, SubLineAllocation,
    InsuranceCertificate, DailyLog, LienWaiver,
    PrimeChangeOrder, SubcontractChangeOrder, OwnerContract,
    PaymentApplication, PayAppLine,
)
from .serializers import (
    CompanySerializer, TeamMemberSerializer, ProjectSerializer, ProjectListSerializer,
    BudgetSerializer, InvoiceSerializer, ProjectScheduleSerializer,
    SubcontractSerializer, SubcontractLineItemSerializer, SubLineAllocationSerializer,
    InsuranceCertificateSerializer, DailyLogSerializer, LienWaiverSerializer,
    PrimeChangeOrderSerializer, SubcontractChangeOrderSerializer, OwnerContractSerializer,
    PaymentApplicationSerializer, PayAppLineSerializer,
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


# ============================================================================
# A1: multi-tenant viewsets — every entity scoped to the requesting user's
# company via Project.company. Optional ?project=<id> filter on list.
# ============================================================================


def _user_company(user):
    """Returns the requesting user's Company, or None if they don't have one."""
    return Company.objects.filter(owner=user).first()


class _CompanyScopedViewSet(viewsets.ModelViewSet):
    """Base for entities owned (transitively) by Company.
    Subclasses set `model` and `project_lookup` (the ORM path from the model
    to a Project foreign key, e.g. 'project' or 'subcontract__project')."""
    permission_classes = [IsAuthenticated]
    model = None
    project_lookup = 'project'

    def get_queryset(self):
        company = _user_company(self.request.user)
        if not company:
            return self.model.objects.none()
        qs = self.model.objects.filter(**{f'{self.project_lookup}__company': company})
        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(**{self.project_lookup: project_id})
        return qs


class SubcontractViewSet(_CompanyScopedViewSet):
    """Subcontracts on the user's company's projects.
    Filter by project: GET /api/subcontracts/?project=<id>"""
    model = Subcontract
    serializer_class = SubcontractSerializer
    project_lookup = 'project'


class SubcontractLineItemViewSet(_CompanyScopedViewSet):
    """Line items inside a subcontract.
    Filter by subcontract: GET /api/subcontract-line-items/?subcontract=<uuid>"""
    model = SubcontractLineItem
    serializer_class = SubcontractLineItemSerializer
    project_lookup = 'subcontract__project'

    def get_queryset(self):
        qs = super().get_queryset()
        sub_id = self.request.query_params.get('subcontract')
        if sub_id:
            qs = qs.filter(subcontract_id=sub_id)
        return qs


class SubLineAllocationViewSet(_CompanyScopedViewSet):
    """Allocations from invoices to specific subcontract line items."""
    model = SubLineAllocation
    serializer_class = SubLineAllocationSerializer
    project_lookup = 'subcontract__project'

    def get_queryset(self):
        qs = super().get_queryset()
        sub_id = self.request.query_params.get('subcontract')
        if sub_id:
            qs = qs.filter(subcontract_id=sub_id)
        invoice_id = self.request.query_params.get('invoice')
        if invoice_id:
            qs = qs.filter(invoice_id=invoice_id)
        return qs


class InsuranceCertificateViewSet(_CompanyScopedViewSet):
    """COIs per subcontract.
    Filter by subcontract: GET /api/insurance-certificates/?subcontract=<uuid>
    Filter by status:      GET /api/insurance-certificates/?status=expired"""
    model = InsuranceCertificate
    serializer_class = InsuranceCertificateSerializer
    project_lookup = 'subcontract__project'

    def get_queryset(self):
        qs = super().get_queryset()
        sub_id = self.request.query_params.get('subcontract')
        if sub_id:
            qs = qs.filter(subcontract_id=sub_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            # status is computed per-row; filter post-fetch.
            qs = [c for c in qs if c.status == status_filter]
        return qs

    @action(detail=False, methods=['get'])
    def needing_attention(self, request):
        """Certs that are expired or expiring within 60 days."""
        company = _user_company(request.user)
        if not company:
            return Response([])
        qs = InsuranceCertificate.objects.filter(subcontract__project__company=company)
        results = [c for c in qs if c.status in ('expired', 'expiring_this_month', 'expiring_soon')]
        results.sort(key=lambda c: c.days_until_expiration if c.days_until_expiration is not None else 99999)
        return Response(InsuranceCertificateSerializer(results, many=True).data)


class DailyLogViewSet(_CompanyScopedViewSet):
    """Daily reports per project.
    Filter by project: GET /api/daily-logs/?project=<id>
    Filter by date range: GET /api/daily-logs/?from=YYYY-MM-DD&to=YYYY-MM-DD"""
    model = DailyLog
    serializer_class = DailyLogSerializer
    project_lookup = 'project'

    def get_queryset(self):
        qs = super().get_queryset()
        d_from = self.request.query_params.get('from')
        d_to = self.request.query_params.get('to')
        if d_from:
            qs = qs.filter(log_date__gte=d_from)
        if d_to:
            qs = qs.filter(log_date__lte=d_to)
        return qs


class LienWaiverViewSet(_CompanyScopedViewSet):
    """Lien waivers per project.
    Filter: ?project=<id>  ?subcontract=<uuid>  ?status=draft|sent|signed|void"""
    model = LienWaiver
    serializer_class = LienWaiverSerializer
    project_lookup = 'project'

    def get_queryset(self):
        qs = super().get_queryset()
        sub_id = self.request.query_params.get('subcontract')
        if sub_id:
            qs = qs.filter(subcontract_id=sub_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs




# ============================================================================
# A1.5: Change Orders + Pay Applications viewsets
# ============================================================================


class PrimeChangeOrderViewSet(_CompanyScopedViewSet):
    """Owner change orders, scoped to user's projects.
    Filters: ?project=<id>  ?status=pending|approved|rejected"""
    model = PrimeChangeOrder
    serializer_class = PrimeChangeOrderSerializer
    project_lookup = 'project'

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=False, methods=['get'])
    def approved_total(self, request):
        """Sum of approved prime CO amounts. Use for "effective contract = original + this".
        Required filter: ?project=<id>"""
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({'error': 'project query param required'}, status=400)
        company = _user_company(request.user)
        if not company:
            return Response({'approved_total': 0})
        from django.db.models import Sum
        total = (PrimeChangeOrder.objects
                 .filter(project__company=company, project_id=project_id, status='approved')
                 .aggregate(t=Sum('approved_amount'))['t'] or 0)
        return Response({'approved_total': total})


class SubcontractChangeOrderViewSet(_CompanyScopedViewSet):
    """Subcontract change orders, scoped to user's projects.
    Filters: ?subcontract=<uuid>  ?status=pending|approved|rejected"""
    model = SubcontractChangeOrder
    serializer_class = SubcontractChangeOrderSerializer
    project_lookup = 'subcontract__project'

    def get_queryset(self):
        qs = super().get_queryset()
        sub_id = self.request.query_params.get('subcontract')
        if sub_id:
            qs = qs.filter(subcontract_id=sub_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class OwnerContractViewSet(_CompanyScopedViewSet):
    """Owner contract metadata, one per project. PK is project_id (OneToOne)."""
    model = OwnerContract
    serializer_class = OwnerContractSerializer
    project_lookup = 'project'


class PaymentApplicationViewSet(_CompanyScopedViewSet):
    """AIA G702/G703 pay applications, scoped to user's projects.
    Filters: ?project=<id>  ?status=draft|submitted|approved|paid"""
    model = PaymentApplication
    serializer_class = PaymentApplicationSerializer
    project_lookup = 'project'

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class PayAppLineViewSet(_CompanyScopedViewSet):
    """G703 SOV line items.
    Filter by pay app: ?pay_app=<uuid>"""
    model = PayAppLine
    serializer_class = PayAppLineSerializer
    project_lookup = 'pay_app__project'

    def get_queryset(self):
        qs = super().get_queryset()
        pay_app_id = self.request.query_params.get('pay_app')
        if pay_app_id:
            qs = qs.filter(pay_app_id=pay_app_id)
        return qs


# ============================================================================
# A1.6 viewsets: Tasks + Schedule + Phases + Budget lines + Allocations
# All scoped via _CompanyScopedViewSet — Project FK chain enforces tenancy.
# ============================================================================

from .models import (
    ProjectPhase, ScheduleItem, ProjectTask, Subtask, TaskComment,
    TaskHandoff, TaskWatcher, TaskTemplate, BudgetLineItem, BudgetAllocation,
)
from .serializers import (
    ProjectPhaseSerializer, ScheduleItemSerializer, ProjectTaskSerializer,
    SubtaskSerializer, TaskCommentSerializer, TaskHandoffSerializer,
    TaskWatcherSerializer, TaskTemplateSerializer,
    BudgetLineItemSerializer, BudgetAllocationSerializer,
)


class ProjectPhaseViewSet(_CompanyScopedViewSet):
    """Per-project phases. Filter: ?project=<id>"""
    model = ProjectPhase
    serializer_class = ProjectPhaseSerializer
    project_lookup = 'project'


class ScheduleItemViewSet(_CompanyScopedViewSet):
    """Unified schedule entries (tasks/milestones/look-ahead/submittals/RFIs).
    Filters: ?project=<id>  ?kind=task|milestone|look_ahead|submittal|rfi
             ?approval_status=open|submitted|...   ?phase=<uuid>"""
    model = ScheduleItem
    serializer_class = ScheduleItemSerializer
    project_lookup = 'project'

    def get_queryset(self):
        qs = super().get_queryset()
        for param in ('kind', 'approval_status', 'phase', 'trade'):
            val = self.request.query_params.get(param)
            if val:
                qs = qs.filter(**{param: val})
        return qs


class ProjectTaskViewSet(_CompanyScopedViewSet):
    """Hand-off-aware project tasks. Filter: ?project=<id>  ?status=open|...
    ?assigned_to=<team_member_id>  ?phase=<uuid>  ?category=punch|..."""
    model = ProjectTask
    serializer_class = ProjectTaskSerializer
    project_lookup = 'project'

    def get_queryset(self):
        qs = super().get_queryset()
        for param in ('status', 'assigned_to', 'phase', 'category', 'priority'):
            val = self.request.query_params.get(param)
            if val:
                qs = qs.filter(**{param: val})
        return qs


class SubtaskViewSet(_CompanyScopedViewSet):
    """Subtasks under a ProjectTask. Filter: ?task=<uuid>"""
    model = Subtask
    serializer_class = SubtaskSerializer
    project_lookup = 'task__project'

    def get_queryset(self):
        qs = super().get_queryset()
        task_id = self.request.query_params.get('task')
        if task_id:
            qs = qs.filter(task_id=task_id)
        return qs


class TaskCommentViewSet(_CompanyScopedViewSet):
    """Comments on tasks. Filter: ?task=<uuid>"""
    model = TaskComment
    serializer_class = TaskCommentSerializer
    project_lookup = 'task__project'

    def get_queryset(self):
        qs = super().get_queryset()
        task_id = self.request.query_params.get('task')
        if task_id:
            qs = qs.filter(task_id=task_id)
        return qs


class TaskHandoffViewSet(_CompanyScopedViewSet):
    """Handoff audit trail. Filter: ?task=<uuid>"""
    model = TaskHandoff
    serializer_class = TaskHandoffSerializer
    project_lookup = 'task__project'

    def get_queryset(self):
        qs = super().get_queryset()
        task_id = self.request.query_params.get('task')
        if task_id:
            qs = qs.filter(task_id=task_id)
        return qs


class TaskWatcherViewSet(_CompanyScopedViewSet):
    """Task watchers join table. Filter: ?task=<uuid>  ?team_member=<id>"""
    model = TaskWatcher
    serializer_class = TaskWatcherSerializer
    project_lookup = 'task__project'

    def get_queryset(self):
        qs = super().get_queryset()
        task_id = self.request.query_params.get('task')
        if task_id:
            qs = qs.filter(task_id=task_id)
        member_id = self.request.query_params.get('team_member')
        if member_id:
            qs = qs.filter(team_member_id=member_id)
        return qs


class TaskTemplateViewSet(viewsets.ModelViewSet):
    """Reusable task templates, scoped per Company (not per project)."""
    serializer_class = TaskTemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        company = _user_company(self.request.user)
        if not company:
            return TaskTemplate.objects.none()
        return TaskTemplate.objects.filter(company=company)

    def perform_create(self, serializer):
        company = _user_company(self.request.user)
        serializer.save(company=company)


class BudgetLineItemViewSet(_CompanyScopedViewSet):
    """CSI-coded budget line items. Filter: ?project=<id>"""
    model = BudgetLineItem
    serializer_class = BudgetLineItemSerializer
    project_lookup = 'project'


class BudgetAllocationViewSet(_CompanyScopedViewSet):
    """Invoice-to-budget-line-item allocations. Filter: ?invoice=<id>  ?line_item=<uuid>"""
    model = BudgetAllocation
    serializer_class = BudgetAllocationSerializer
    project_lookup = 'invoice__project'

    def get_queryset(self):
        qs = super().get_queryset()
        inv_id = self.request.query_params.get('invoice')
        if inv_id:
            qs = qs.filter(invoice_id=inv_id)
        line_id = self.request.query_params.get('line_item')
        if line_id:
            qs = qs.filter(line_item_id=line_id)
        return qs
