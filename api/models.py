import uuid
from datetime import date as _date, timedelta

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


# ============================================================================
# Multi-tenant foundation (A1) — entities currently Mac-local in UserDefaults.
# UUID primary keys so the Mac client can keep its existing IDs across sync.
# ============================================================================


class Subcontract(models.Model):
    """A subcontract awarded to a vendor on a project. Multi-line: each line
    has its own CSI code + amount, summed for the contract value."""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='subcontracts')

    name = models.CharField(max_length=255)
    vendor_name = models.CharField(max_length=255)
    vendor_email = models.EmailField(blank=True)
    vendor_phone = models.CharField(max_length=30, blank=True)

    scope = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.vendor_name} · {self.name}"

    @property
    def contract_amount(self):
        return sum((li.amount for li in self.line_items.all()), 0)


class SubcontractLineItem(models.Model):
    """One scope-of-work line within a subcontract."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subcontract = models.ForeignKey(Subcontract, on_delete=models.CASCADE, related_name='line_items')

    description = models.CharField(max_length=500, blank=True)
    csi_code = models.CharField(max_length=20, blank=True)
    csi_title = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return f"{self.csi_code} {self.description}"[:80]


class SubLineAllocation(models.Model):
    """A vendor invoice billed against one specific subcontract line item.
    One invoice can split across multiple lines via multiple allocations."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='sub_line_allocations')
    subcontract = models.ForeignKey(Subcontract, on_delete=models.CASCADE, related_name='allocations')
    line_item = models.ForeignKey(SubcontractLineItem, on_delete=models.CASCADE, related_name='allocations')

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    allocation_date = models.DateField(default=_date.today)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-allocation_date']
        indexes = [
            models.Index(fields=['subcontract']),
            models.Index(fields=['invoice']),
        ]

    def __str__(self):
        return f"${self.amount} · inv {self.invoice_id} → line {self.line_item_id}"


class InsuranceCertificate(models.Model):
    """COI (Certificate of Insurance) tracked per subcontract per coverage type."""
    COVERAGE_CHOICES = [
        ('general_liability', 'General Liability'),
        ('workers_comp',      "Workers' Comp"),
        ('auto_liability',    'Auto Liability'),
        ('umbrella',          'Umbrella / Excess'),
        ('builders_risk',     'Builders Risk'),
        ('professional',      'Professional'),
        ('pollution',         'Pollution'),
        ('other',             'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subcontract = models.ForeignKey(Subcontract, on_delete=models.CASCADE, related_name='insurance_certificates')

    coverage_type = models.CharField(max_length=30, choices=COVERAGE_CHOICES, default='general_liability')
    carrier = models.CharField(max_length=255, blank=True)
    policy_number = models.CharField(max_length=100, blank=True)

    effective_date = models.DateField(blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)

    coverage_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    aggregate_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    additional_insured = models.BooleanField(default=False)
    waiver_of_subrogation = models.BooleanField(default=False)
    primary_and_non_contributory = models.BooleanField(default=False)

    notes = models.TextField(blank=True)
    last_reminder_sent = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['expiration_date', 'coverage_type']

    def __str__(self):
        return f"{self.subcontract.vendor_name} · {self.get_coverage_type_display()}"

    @property
    def days_until_expiration(self):
        if not self.expiration_date:
            return None
        return (self.expiration_date - _date.today()).days

    @property
    def status(self):
        days = self.days_until_expiration
        if days is None:
            return 'missing'
        if days < 0:
            return 'expired'
        if days <= 30:
            return 'expiring_this_month'
        if days <= 60:
            return 'expiring_soon'
        return 'active'


class DailyLog(models.Model):
    """Construction-standard daily report. One row per project per calendar day."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='daily_logs')

    log_date = models.DateField()
    weather = models.CharField(max_length=255, blank=True)
    temp_high_f = models.CharField(max_length=10, blank=True)
    temp_low_f = models.CharField(max_length=10, blank=True)

    crew_size = models.IntegerField(default=0)
    crew_notes = models.TextField(blank=True)
    work_performed = models.TextField(blank=True)
    materials_delivered = models.TextField(blank=True)
    equipment_on_site = models.TextField(blank=True)
    issues = models.TextField(blank=True)
    visitors = models.TextField(blank=True)

    photo_filenames = models.JSONField(default=list, blank=True)
    author_name = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-log_date']
        indexes = [models.Index(fields=['project', '-log_date'])]

    def __str__(self):
        return f"Daily log {self.log_date} · {self.project.name}"


class LienWaiver(models.Model):
    """Lien waiver issued to (or received from) a party for a specific pay period.
    Required reading for commercial subs and GCs — the document that releases
    lien rights against an owner's property in exchange for payment."""
    TYPE_CHOICES = [
        ('cond_partial',   'Conditional Partial'),
        ('uncond_partial', 'Unconditional Partial'),
        ('cond_final',     'Conditional Final'),
        ('uncond_final',   'Unconditional Final'),
    ]
    STATUS_CHOICES = [
        ('draft',  'Draft'),
        ('sent',   'Sent'),
        ('signed', 'Signed'),
        ('void',   'Void'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='lien_waivers')
    subcontract = models.ForeignKey(
        Subcontract, on_delete=models.SET_NULL,
        related_name='lien_waivers', null=True, blank=True,
    )

    waiver_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Parties named on the waiver document.
    claimant_name = models.CharField(max_length=255, help_text='The contractor/sub releasing lien rights')
    customer_name = models.CharField(max_length=255, blank=True, help_text='Who the claimant is contracting with (often the GC)')
    owner_name = models.CharField(max_length=255, blank=True, help_text='Property owner')
    job_address = models.TextField(blank=True)
    job_description = models.TextField(blank=True)

    # Period + money
    through_date = models.DateField(help_text='Waiver covers all work performed/payments received through this date')
    amount = models.DecimalField(max_digits=14, decimal_places=2, help_text='Amount being released (paid or expected to be paid)')

    # Signature block
    signed_by = models.CharField(max_length=255, blank=True)
    signed_date = models.DateField(blank=True, null=True)
    notary_name = models.CharField(max_length=255, blank=True, help_text='For unconditional waivers that require notarization')

    # Generated PDF (filename relative to the waivers folder in Application Support)
    pdf_filename = models.CharField(max_length=255, blank=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-through_date', '-created_at']
        indexes = [
            models.Index(fields=['project', '-through_date']),
            models.Index(fields=['subcontract']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.get_waiver_type_display()} · {self.claimant_name} · {self.through_date}"


# ============================================================================
# Multi-tenant foundation A1.5 — Change Orders + Pay Applications.
# Same patterns as A1: UUID PKs, company scoping via Project.
# ============================================================================


class PrimeChangeOrder(models.Model):
    """Change order between us and the OWNER. When approved, raises (or lowers)
    the project's effective contract value. We never edit Project.contract_amount —
    the running total is computed as `original + sum(approved primes)`."""
    STATUS_CHOICES = [
        ('pending',  'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='prime_change_orders')

    number = models.CharField(max_length=50, blank=True, help_text='"PCO-001", "CO-12", whatever the GC uses')
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    justification = models.TextField(blank=True, help_text='Why the change is needed')

    requested_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                           help_text='Can be negative for credits')
    requested_date = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    approved_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                          help_text='May differ from requested')
    approved_date = models.DateField(blank=True, null=True)
    approved_by = models.CharField(max_length=255, blank=True, help_text='Owner rep / signer name')
    rejected_reason = models.TextField(blank=True)

    photo_filenames = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
        ]

    def __str__(self):
        return f"PCO {self.number} · {self.title or '(untitled)'} · {self.status}"


class SubcontractChangeOrder(models.Model):
    """Change order between us and a SUBCONTRACTOR. When approved, raises (or
    lowers) that subcontract's effective value."""
    STATUS_CHOICES = PrimeChangeOrder.STATUS_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subcontract = models.ForeignKey(Subcontract, on_delete=models.CASCADE,
                                     related_name='change_orders')

    number = models.CharField(max_length=50, blank=True)
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    justification = models.TextField(blank=True)

    requested_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    requested_date = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    approved_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    approved_date = models.DateField(blank=True, null=True)
    approved_by = models.CharField(max_length=255, blank=True)
    rejected_reason = models.TextField(blank=True)

    photo_filenames = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['subcontract', 'status']),
        ]

    def __str__(self):
        return f"SubCO {self.number} · {self.title or '(untitled)'} · {self.status}"


class OwnerContract(models.Model):
    """Contract metadata that doesn't fit on Project (signing date, contract type,
    owner rep contact, free-text notes). One per project."""
    CONTRACT_TYPE_CHOICES = [
        ('lump_sum',     'Lump Sum / Fixed Price'),
        ('cost_plus',    'Cost Plus'),
        ('gmp',          'Guaranteed Maximum Price (GMP)'),
        ('time_and_mat', 'Time & Materials'),
        ('unit_price',   'Unit Price'),
        ('other',        'Other'),
    ]

    project = models.OneToOneField(Project, on_delete=models.CASCADE,
                                    related_name='owner_contract', primary_key=True)

    contract_number = models.CharField(max_length=100, blank=True)
    contract_type = models.CharField(max_length=20, choices=CONTRACT_TYPE_CHOICES, blank=True)
    signed_date = models.DateField(blank=True, null=True)

    owner_name = models.CharField(max_length=255, blank=True, help_text='Owner / client legal name')
    owner_rep_name = models.CharField(max_length=255, blank=True)
    owner_rep_email = models.EmailField(blank=True)
    owner_rep_phone = models.CharField(max_length=30, blank=True)

    notes = models.TextField(blank=True)
    attachment_filenames = models.JSONField(default=list, blank=True,
                                             help_text='Signed PDF, exhibits, etc.')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Owner contract for {self.project.name}"


class PaymentApplication(models.Model):
    """AIA G702/G703 progress billing. One per (project, period). Lines stored
    in PayAppLine. G702 totals are computed properties on the Python side."""
    STATUS_CHOICES = [
        ('draft',     'Draft'),
        ('submitted', 'Submitted'),
        ('approved',  'Approved'),
        ('paid',      'Paid'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE,
                                 related_name='payment_applications')

    application_number = models.IntegerField(help_text='1, 2, 3, ... per project')
    application_date = models.DateField(blank=True, null=True)
    period_from = models.DateField(blank=True, null=True)
    period_to = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    retainage_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10,
                                            help_text='App-level default; lines can override')

    # Snapshotted contract values so historic apps don't shift if the project's
    # contract or COs change later.
    original_contract_sum = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_change_orders_at_submission = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-application_number']
        indexes = [
            models.Index(fields=['project', '-application_number']),
        ]
        unique_together = ('project', 'application_number')

    def __str__(self):
        return f"Pay App #{self.application_number} · {self.project.name}"

    @property
    def contract_sum_to_date(self):
        return self.original_contract_sum + self.net_change_orders_at_submission

    @property
    def total_completed_and_stored_to_date(self):
        return sum((li.total_completed_and_stored for li in self.lines.all()), 0)

    @property
    def total_retainage(self):
        rate = self.retainage_percent
        return sum((li.retainage_amount(rate) for li in self.lines.all()), 0)

    @property
    def total_earned_less_retainage(self):
        return self.total_completed_and_stored_to_date - self.total_retainage


class PayAppLine(models.Model):
    """G703 Schedule of Values row. Belongs to a PaymentApplication."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pay_app = models.ForeignKey(PaymentApplication, on_delete=models.CASCADE, related_name='lines')

    item_number = models.CharField(max_length=20, blank=True, help_text='"1", "2.1", "CO-3", etc.')
    csi_code = models.CharField(max_length=20, blank=True)
    description = models.CharField(max_length=500, blank=True)

    scheduled_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    work_completed_from_previous = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    work_completed_this_period = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    materials_stored = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    retainage_percent_override = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Per-line retainage override. Use 0 to inherit the app-level rate.',
    )

    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'item_number']

    def __str__(self):
        return f"{self.item_number} · {self.description}"[:80]

    @property
    def total_completed_and_stored(self):
        return (self.work_completed_from_previous
                + self.work_completed_this_period
                + self.materials_stored)

    @property
    def percent_complete(self):
        if self.scheduled_value <= 0:
            return 0
        return float(self.total_completed_and_stored) / float(self.scheduled_value) * 100

    @property
    def balance_to_finish(self):
        return self.scheduled_value - self.total_completed_and_stored

    def retainage_amount(self, app_rate):
        rate = self.retainage_percent_override if self.retainage_percent_override > 0 else app_rate
        return self.total_completed_and_stored * rate / 100
