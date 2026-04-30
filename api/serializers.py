from rest_framework import serializers
from .models import (
    Company, TeamMember, Project, Budget, Invoice, ProjectSchedule,
    Subcontract, SubcontractLineItem, SubLineAllocation,
    InsuranceCertificate, DailyLog, LienWaiver,
)

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'name', 'email', 'phone', 'address', 'city', 'state', 'zip_code', 'qb_connected', 'created_at']
        read_only_fields = ['id', 'created_at']


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
    class Meta:
        model = SubcontractLineItem
        fields = [
            'id', 'subcontract', 'description', 'csi_code', 'csi_title',
            'amount', 'notes', 'sort_order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class SubcontractSerializer(serializers.ModelSerializer):
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
