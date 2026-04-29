from rest_framework import serializers
from .models import Company, TeamMember, Project, Budget, Invoice, ProjectSchedule

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


