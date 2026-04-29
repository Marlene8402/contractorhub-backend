from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Company(models.Model):
    """Contractor company profile"""
    owner = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    
    # QB Integration
    qb_access_token = models.TextField(blank=True, null=True)
    qb_refresh_token = models.TextField(blank=True, null=True)
    qb_realm_id = models.CharField(max_length=100, blank=True)
    qb_token_expires_at = models.DateTimeField(blank=True, null=True)
    qb_connected = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class TeamMember(models.Model):
    """Team members/employees"""
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('pm', 'Project Manager'),
        ('foreman', 'Foreman'),
        ('crew', 'Crew'),
        ('office', 'Office Staff'),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='team_members')
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='crew')
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Project(models.Model):
    """Construction projects"""
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('bidding', 'Bidding'),
        ('awarded', 'Awarded'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('closed', 'Closed'),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='projects')
    project_manager = models.ForeignKey(TeamMember, on_delete=models.SET_NULL, null=True, related_name='managed_projects')
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    
    # Contract Info
    contract_number = models.CharField(max_length=100, blank=True, unique=True)
    client_name = models.CharField(max_length=255)
    contract_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Timeline
    bid_due_date = models.DateField(blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField()
    
    # QB Integration
    qb_customer_id = models.CharField(max_length=100, blank=True)
    qb_project_id = models.CharField(max_length=100, blank=True)
    qb_synced = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created_at']


class Budget(models.Model):
    """Project budgets and tracking"""
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='budget')
    
    estimated_labor = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estimated_materials = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estimated_equipment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estimated_overhead = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estimated_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    actual_labor = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_materials = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_equipment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_overhead = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Budget for {self.project.name}"

    @property
    def estimated_total(self):
        return (self.estimated_labor + self.estimated_materials + 
                self.estimated_equipment + self.estimated_overhead + self.estimated_profit)
    
    @property
    def actual_total(self):
        return (self.actual_labor + self.actual_materials + 
                self.actual_equipment + self.actual_overhead)
    
    @property
    def variance(self):
        return self.estimated_total - self.actual_total


class Invoice(models.Model):
    """Invoices to clients"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('viewed', 'Viewed'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=100, unique=True)
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    paid_date = models.DateField(blank=True, null=True)
    
    # QB Integration
    qb_invoice_id = models.CharField(max_length=100, blank=True)
    qb_synced = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Invoice {self.invoice_number}"

    class Meta:
        ordering = ['-issue_date']


class QBAccount(models.Model):
    """One QB OAuth connection per Django user."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='qb_account')
    access_token = models.TextField()
    refresh_token = models.TextField()
    token_expires_at = models.DateTimeField()
    realm_id = models.CharField(max_length=20)
    is_connected = models.BooleanField(default=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - QB Account"


class QBGLMapping(models.Model):
    """Maps a CSI cost code (or category) to a QB GL account."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='qb_gl_mappings')
    category = models.CharField(max_length=50)
    gl_account_number = models.CharField(max_length=20)
    gl_account_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'category')
        ordering = ['category']

    def __str__(self):
        return f"{self.user.username} · {self.category} → {self.gl_account_number}"


class QBSyncLog(models.Model):
    """Audit log of every QB sync attempt with full retry / error tracking."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('syncing', 'Syncing'),
        ('success', 'Success'),
        ('failed',  'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='qb_sync_logs')
    sync_type = models.CharField(max_length=20)
    object_id = models.CharField(max_length=50)
    object_type = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    attempt_count = models.IntegerField(default=0)
    qb_transaction_id = models.CharField(max_length=100, null=True, blank=True)
    idempotency_key = models.CharField(max_length=100, unique=True)
    error_message = models.TextField(null=True, blank=True)
    error_code = models.CharField(max_length=50, null=True, blank=True)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['idempotency_key']),
        ]

    def __str__(self):
        return f"{self.object_type} {self.object_id} · {self.status}"


class ProjectSchedule(models.Model):
    """Track project milestones and timeline"""
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='schedule')
    
    planned_start = models.DateField()
    planned_end = models.DateField()
    actual_start = models.DateField(blank=True, null=True)
    actual_end = models.DateField(blank=True, null=True)
    
    percent_complete = models.IntegerField(default=0)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Schedule for {self.project.name}"
