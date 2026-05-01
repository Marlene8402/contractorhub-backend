from rest_framework import serializers
from .models import (
    Company, TeamMember, Project, Budget, Invoice, ProjectSchedule,
    Subcontract, SubcontractLineItem, SubLineAllocation,
    InsuranceCertificate, DailyLog, LienWaiver,
    PrimeChangeOrder, SubcontractChangeOrder, OwnerContract,
    PaymentApplication, PayAppLine,
)

class CompanySerializer(serializers.ModelSerializer):
    has_active_subscription = serializers.ReadOnlyField()

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'email', 'phone', 'address', 'city', 'state', 'zip_code',
            'qb_connected',
            'subscription_tier', 'subscription_status',
            'trial_ends_at', 'current_period_end', 'has_active_subscription',
            'created_at',
        ]
        read_only_fields = [
            'id', 'created_at',
            # Billing fields are mutated only by webhook + signup flows, never
            # by the client directly.
            'subscription_tier', 'subscription_status',
            'trial_ends_at', 'current_period_end', 'has_active_subscription',
        ]


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        fields = ['id', 'first_name', 'last_name', 'email', 'phone', 'role', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class BudgetSerializer(serializers.ModelSerializer):
    estimated_total = serializers.ReadOnlyField()
    actual_total = serializers.ReadOnlyField()
    variance = serializers.ReadOnlyField()
    
    class Meta:
        model = Budget
        fields = [
            'id', 'project', 
            'estimated_labor', 'estimated_materials', 'estimated_equipment', 'estimated_overhead', 'estimated_profit',
            'actual_labor', 'actual_materials', 'actual_equipment', 'actual_overhead',
            'estimated_total', 'actual_total', 'variance',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProjectScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectSchedule
        fields = ['id', 'project', 'planned_start', 'planned_end', 'actual_start', 'actual_end', 'percent_complete', 'notes', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ['id', 'project', 'invoice_number', 'amount', 'description', 'status', 'issue_date', 'due_date', 'paid_date', 'qb_synced', 'created_at', 'updated_at']
        read_only_fields = ['id', 'issue_date', 'created_at', 'updated_at']


class ProjectSerializer(serializers.ModelSerializer):
    budget = BudgetSerializer(read_only=True)
    schedule = ProjectScheduleSerializer(read_only=True)
    invoices = InvoiceSerializer(many=True, read_only=True)
    project_manager_name = serializers.CharField(source='project_manager.get_full_name', read_only=True)
    
    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'status', 'contract_number', 'client_name', 'contract_amount',
            'bid_due_date', 'start_date', 'end_date', 'project_manager', 'project_manager_name',
            'budget', 'schedule', 'invoices', 'qb_synced', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'qb_synced']


class ProjectListSerializer(serializers.ModelSerializer):
    """Lightweight project serializer for list views"""
    project_manager_name = serializers.CharField(source='project_manager.get_full_name', read_only=True)
    
    class Meta:
        model = Project
        fields = ['id', 'name', 'status', 'client_name', 'contract_amount', 'start_date', 'end_date', 'project_manager_name']
        read_only_fields = fields


# ---------- A1: multi-tenant foundation serializers ----------

class SubcontractLineItemSerializer(serializers.ModelSerializer):
    # Accept client-supplied UUIDs so the Mac app's local IDs become the
    # canonical primary keys. Without this, DRF's ModelSerializer treats
    # the PK as auto-generated and silently ignores incoming `id`, breaking
    # FK references from related rows POSTed right after the parent.
    id = serializers.UUIDField(required=False)

    class Meta:
        model = SubcontractLineItem
        fields = [
            'id', 'subcontract', 'description', 'csi_code', 'csi_title',
            'amount', 'notes', 'sort_order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class SubcontractSerializer(serializers.ModelSerializer):
    # See SubcontractLineItemSerializer.id — same rationale.
    id = serializers.UUIDField(required=False)
    line_items = SubcontractLineItemSerializer(many=True, read_only=True)
    contract_amount = serializers.ReadOnlyField()

    class Meta:
        model = Subcontract
        fields = [
            'id', 'project', 'name',
            'vendor_name', 'vendor_email', 'vendor_phone',
            'scope', 'status', 'start_date', 'end_date',
            'contract_amount', 'line_items',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['contract_amount', 'created_at', 'updated_at']


class SubLineAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubLineAllocation
        fields = [
            'id', 'invoice', 'subcontract', 'line_item',
            'amount', 'allocation_date', 'created_at',
        ]
        read_only_fields = ['created_at']


class InsuranceCertificateSerializer(serializers.ModelSerializer):
    days_until_expiration = serializers.ReadOnlyField()
    status = serializers.ReadOnlyField()

    class Meta:
        model = InsuranceCertificate
        fields = [
            'id', 'subcontract', 'coverage_type',
            'carrier', 'policy_number',
            'effective_date', 'expiration_date',
            'coverage_limit', 'aggregate_limit',
            'additional_insured', 'waiver_of_subrogation', 'primary_and_non_contributory',
            'notes', 'last_reminder_sent',
            'days_until_expiration', 'status',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['days_until_expiration', 'status', 'created_at', 'updated_at']


class DailyLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyLog
        fields = [
            'id', 'project', 'log_date',
            'weather', 'temp_high_f', 'temp_low_f',
            'crew_size', 'crew_notes',
            'work_performed', 'materials_delivered', 'equipment_on_site',
            'issues', 'visitors',
            'photo_filenames', 'author_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class LienWaiverSerializer(serializers.ModelSerializer):
    class Meta:
        model = LienWaiver
        fields = [
            'id', 'project', 'subcontract',
            'waiver_type', 'status',
            'claimant_name', 'customer_name', 'owner_name',
            'job_address', 'job_description',
            'through_date', 'amount',
            'signed_by', 'signed_date', 'notary_name',
            'pdf_filename', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


# ---------- A1.5 serializers: Change Orders + Pay Applications ----------


class PrimeChangeOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrimeChangeOrder
        fields = [
            'id', 'project',
            'number', 'title', 'description', 'justification',
            'requested_amount', 'requested_date',
            'status',
            'approved_amount', 'approved_date', 'approved_by', 'rejected_reason',
            'photo_filenames',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class SubcontractChangeOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubcontractChangeOrder
        fields = [
            'id', 'subcontract',
            'number', 'title', 'description', 'justification',
            'requested_amount', 'requested_date',
            'status',
            'approved_amount', 'approved_date', 'approved_by', 'rejected_reason',
            'photo_filenames',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class OwnerContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnerContract
        fields = [
            'project',
            'contract_number', 'contract_type', 'signed_date',
            'owner_name', 'owner_rep_name', 'owner_rep_email', 'owner_rep_phone',
            'notes', 'attachment_filenames',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class PayAppLineSerializer(serializers.ModelSerializer):
    total_completed_and_stored = serializers.ReadOnlyField()
    percent_complete = serializers.ReadOnlyField()
    balance_to_finish = serializers.ReadOnlyField()

    class Meta:
        model = PayAppLine
        fields = [
            'id', 'pay_app',
            'item_number', 'csi_code', 'description',
            'scheduled_value',
            'work_completed_from_previous', 'work_completed_this_period', 'materials_stored',
            'retainage_percent_override',
            'sort_order',
            'total_completed_and_stored', 'percent_complete', 'balance_to_finish',
        ]
        read_only_fields = ['total_completed_and_stored', 'percent_complete', 'balance_to_finish']


class PaymentApplicationSerializer(serializers.ModelSerializer):
    lines = PayAppLineSerializer(many=True, read_only=True)
    contract_sum_to_date = serializers.ReadOnlyField()
    total_completed_and_stored_to_date = serializers.ReadOnlyField()
    total_retainage = serializers.ReadOnlyField()
    total_earned_less_retainage = serializers.ReadOnlyField()

    class Meta:
        model = PaymentApplication
        fields = [
            'id', 'project',
            'application_number', 'application_date', 'period_from', 'period_to',
            'status', 'retainage_percent',
            'original_contract_sum', 'net_change_orders_at_submission',
            'notes',
            'contract_sum_to_date', 'total_completed_and_stored_to_date',
            'total_retainage', 'total_earned_less_retainage',
            'lines',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'contract_sum_to_date', 'total_completed_and_stored_to_date',
            'total_retainage', 'total_earned_less_retainage',
            'created_at', 'updated_at',
        ]


# ---------- A1.6 serializers: Tasks + Schedule + Phases + Budget lines ----------

from .models import (
    ProjectPhase, ScheduleItem, ProjectTask, Subtask, TaskComment,
    TaskHandoff, TaskWatcher, TaskTemplate, BudgetLineItem, BudgetAllocation,
)


class ProjectPhaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectPhase
        fields = [
            'id', 'project', 'name', 'sort_order', 'color_hex',
            'started_at', 'finished_at', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class ScheduleItemSerializer(serializers.ModelSerializer):
    depends_on = serializers.PrimaryKeyRelatedField(
        many=True, queryset=ScheduleItem.objects.all(), required=False,
    )

    class Meta:
        model = ScheduleItem
        fields = [
            'id', 'project',
            'kind', 'title', 'details',
            'start_date', 'end_date', 'percent_complete', 'depends_on',
            'phase',
            'assigned_to', 'assigned_to_name', 'trade', 'location',
            'spec_section', 'submitted_date', 'required_by_date',
            'approved_date', 'approval_status',
            'rfi_number', 'question', 'answer', 'responded_date',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class SubtaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subtask
        fields = [
            'id', 'task', 'title', 'is_done', 'completed_at',
            'due_date', 'sort_order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class TaskCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskComment
        fields = ['id', 'task', 'author', 'author_name', 'text', 'timestamp']
        read_only_fields = ['timestamp']


class TaskHandoffSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskHandoff
        fields = [
            'id', 'task',
            'from_member', 'from_name', 'to_member', 'to_name',
            'note', 'timestamp',
        ]
        read_only_fields = ['timestamp']


class TaskWatcherSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskWatcher
        fields = ['id', 'task', 'team_member', 'created_at']
        read_only_fields = ['created_at']


class ProjectTaskSerializer(serializers.ModelSerializer):
    """Embeds subtasks/comments/handoffs/watchers as nested read-only collections
    to match the Mac client's existing UserDefaults shape (Subtask[], Comment[],
    Handoff[], watcherIDs[]). Writes go through the dedicated child endpoints."""
    subtasks    = SubtaskSerializer(many=True, read_only=True)
    comments    = TaskCommentSerializer(many=True, read_only=True)
    handoffs    = TaskHandoffSerializer(many=True, read_only=True)
    watcher_ids = serializers.SerializerMethodField()

    class Meta:
        model = ProjectTask
        fields = [
            'id', 'project',
            'title', 'details', 'category', 'priority', 'status',
            'assigned_to', 'assigned_to_name',
            'due_date', 'location', 'completed_at',
            'recurrence', 'reminder_days_before', 'last_reminder_sent',
            'phase', 'photo_filenames',
            'subtasks', 'comments', 'handoffs', 'watcher_ids',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_watcher_ids(self, obj):
        return list(obj.watchers.values_list('team_member_id', flat=True))


class TaskTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTemplate
        fields = [
            'id', 'company',
            'name', 'title', 'details', 'category', 'priority', 'location',
            'subtask_titles', 'recurrence', 'reminder_days_before',
            'default_assignee', 'default_assignee_name', 'default_phase_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['company', 'created_at', 'updated_at']


class BudgetLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetLineItem
        fields = [
            'id', 'project', 'csi_code', 'csi_title', 'description',
            'budgeted_amount', 'sort_order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class BudgetAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetAllocation
        fields = [
            'id', 'invoice', 'line_item', 'csi_code',
            'amount', 'allocation_date', 'qb_pushed', 'created_at',
        ]
        read_only_fields = ['created_at']
