import uuid
from datetime import date as _date, timedelta

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Company(models.Model):
    """Contractor company profile"""

    # ---- Subscription tiers (mirror Stripe price IDs in settings) ----
    TIER_STARTER = 'starter'
    TIER_PRO     = 'pro'
    TIER_SCALE   = 'scale'
    TIER_CHOICES = [
        (TIER_STARTER, 'Starter'),
        (TIER_PRO,     'Pro'),
        (TIER_SCALE,   'Scale'),
    ]

    # Subscription status mirrors a subset of Stripe's subscription.status
    # plus 'none' for "never subscribed, trial expired".
    STATUS_TRIALING = 'trialing'
    STATUS_ACTIVE   = 'active'
    STATUS_PAST_DUE = 'past_due'
    STATUS_CANCELED = 'canceled'
    STATUS_NONE     = 'none'
    STATUS_CHOICES = [
        (STATUS_TRIALING, 'Trialing'),
        (STATUS_ACTIVE,   'Active'),
        (STATUS_PAST_DUE, 'Past Due'),
        (STATUS_CANCELED, 'Canceled'),
        (STATUS_NONE,     'None'),
    ]

    # QB integration mode — drives which QBService implementation handles
    # this Company's writes. See QB_INTEGRATION_v2_SPEC.md §4.
    QB_MODE_CHOICES = [
        ('qbo',  'QuickBooks Online (REST API)'),
        ('qbwc', 'QuickBooks Desktop (Web Connector polled SOAP)'),
        ('',     'Not connected'),
    ]

    owner = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)

    # QB Integration (legacy; kept for backwards compat with the existing
    # QBO OAuth code in qb_views.py until that's refactored to use QBOService).
    qb_access_token = models.TextField(blank=True, null=True)
    qb_refresh_token = models.TextField(blank=True, null=True)
    qb_realm_id = models.CharField(max_length=100, blank=True)
    qb_token_expires_at = models.DateTimeField(blank=True, null=True)
    qb_connected = models.BooleanField(default=False)

    # QB v2 fields (Session B). qb_mode picks the QBService implementation;
    # qbwc_password is the shared secret in the Web Connector .qwc file
    # (only used when qb_mode == 'qbwc').
    qb_mode = models.CharField(max_length=10, choices=QB_MODE_CHOICES, blank=True, default='',
                               help_text="Drives QBService factory dispatch.")
    qbwc_password   = models.CharField(max_length=64, blank=True,
                                        help_text="Shared secret for QB Web Connector authentication.")
    qb_last_synced_at = models.DateTimeField(blank=True, null=True,
                                             help_text="Timestamp of last successful QBSyncLog row for this Company.")

    # Stripe billing
    stripe_customer_id     = models.CharField(max_length=64, blank=True)
    stripe_subscription_id = models.CharField(max_length=64, blank=True)
    subscription_tier      = models.CharField(max_length=20, choices=TIER_CHOICES, blank=True)
    subscription_status    = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                              default=STATUS_TRIALING)
    trial_ends_at          = models.DateTimeField(blank=True, null=True)
    current_period_end     = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def has_active_subscription(self):
        """True if the company can use the product right now.

        Trial counts as active until trial_ends_at. After that we require a
        real Stripe subscription in 'active' or 'trialing' state. 'past_due'
        gets a grace period (Stripe retries cards for ~3 weeks before going
        'canceled') so we keep them in.
        """
        if self.subscription_status == self.STATUS_TRIALING:
            if self.trial_ends_at and timezone.now() <= self.trial_ends_at:
                return True
            # Stripe-driven trial (after they've added a card and Stripe is
            # tracking trial_end on the subscription itself).
            return bool(self.stripe_subscription_id)
        return self.subscription_status in (self.STATUS_ACTIVE, self.STATUS_PAST_DUE)


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

    # 1099 flag — required for the Vendor record we push to QuickBooks.
    # Subcontractors paid as 1099 contractors get flagged so QB tracks them
    # for year-end 1099-NEC filing. Default False; user toggles per sub.
    is_1099_vendor = models.BooleanField(default=False,
                                         help_text="Pay this vendor on a 1099 (mirrors QB Vendor.Vendor1099).")
    vendor_tax_id  = models.CharField(max_length=20, blank=True,
                                      help_text="EIN or SSN, for 1099-NEC reporting. Stored as-is; surface masked in UI.")

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


# ============================================================================
# A1.6: Tasks + Schedule + ProjectPhase + Budget line items + Invoice allocations
# Mirrors what the Mac app currently stores in UserDefaults (see ProjectTaskStore,
# ScheduleStore, BudgetStore in ContractorHubMac/Sources/). UUID PKs so the Mac
# client keeps its existing IDs across sync. Subtasks/comments/handoffs/watchers
# are real FK rows on the backend (better querying) but the ProjectTask
# serializer returns them embedded to match the Mac client's existing shape.
# ============================================================================


class ProjectPhase(models.Model):
    """Per-project phase (Pre-Construction, Mobilization, Foundation, Drywall, ...).
    Mac app currently uses a fixed enum (bidding/post_award/in_progress/closeout);
    the backend supports custom phases per project. New projects get the four
    Mac defaults seeded by ProjectViewSet.perform_create."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='phases')

    name       = models.CharField(max_length=100)
    sort_order = models.IntegerField(default=0)
    color_hex  = models.CharField(max_length=9, blank=True, help_text='Optional UI tint, e.g. "#1F6FEB"')

    started_at  = models.DateField(blank=True, null=True)
    finished_at = models.DateField(blank=True, null=True)
    is_active   = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['project', 'sort_order', 'name']
        unique_together = ('project', 'name')

    def __str__(self):
        return f"{self.project.name} · {self.name}"


class ScheduleItem(models.Model):
    """Unified schedule entry. The Mac app's ScheduleStore stores a single
    polymorphic struct discriminated by `kind` (task/milestone/submittal/rfi)
    plus shared date/assignment fields and kind-specific extras. We mirror
    that shape so the Mac client can sync without reshaping."""
    KIND_CHOICES = [
        ('task',       'Gantt Task'),
        ('milestone',  'Milestone'),
        ('look_ahead', 'Look-Ahead'),
        ('submittal',  'Submittal'),
        ('rfi',        'RFI'),
    ]
    APPROVAL_CHOICES = [
        ('open',             'Open'),
        ('submitted',        'Submitted'),
        ('revise_resubmit',  'Revise & Resubmit'),
        ('approved',         'Approved'),
        ('rejected',         'Rejected'),
        ('answered',         'Answered'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='schedule_items')

    kind    = models.CharField(max_length=20, choices=KIND_CHOICES, default='task')
    title   = models.CharField(max_length=255)
    details = models.TextField(blank=True)

    # Common timing
    start_date       = models.DateField(blank=True, null=True)
    end_date         = models.DateField(blank=True, null=True)
    percent_complete = models.IntegerField(default=0)
    depends_on       = models.ManyToManyField('self', symmetrical=False, blank=True,
                                              related_name='dependents')

    phase = models.ForeignKey(ProjectPhase, on_delete=models.SET_NULL,
                              null=True, blank=True, related_name='schedule_items')

    # Common assignment
    assigned_to      = models.ForeignKey(TeamMember, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='schedule_items')
    assigned_to_name = models.CharField(max_length=255, blank=True,
                                        help_text='Snapshot of assignee name at assignment time')
    trade            = models.CharField(max_length=100, blank=True, help_text='"Electrical", "Plumbing" — used by look-ahead grouping')
    location         = models.CharField(max_length=255, blank=True)

    # Submittal-specific
    spec_section      = models.CharField(max_length=100, blank=True, help_text='CSI section, e.g. "07 21 13 — Insulation"')
    submitted_date    = models.DateField(blank=True, null=True)
    required_by_date  = models.DateField(blank=True, null=True)
    approved_date     = models.DateField(blank=True, null=True)
    approval_status   = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='open')

    # RFI-specific
    rfi_number      = models.CharField(max_length=50, blank=True)
    question        = models.TextField(blank=True)
    answer          = models.TextField(blank=True)
    responded_date  = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['project', 'start_date', 'created_at']
        indexes = [
            models.Index(fields=['project', 'kind']),
            models.Index(fields=['project', 'start_date']),
        ]

    def __str__(self):
        return f"[{self.get_kind_display()}] {self.title}"


class ProjectTask(models.Model):
    """Hand-off-aware task with status flow open → in_progress → needs_verification → done.
    Mirrors the Mac app's ProjectTask struct. Subtasks/comments/handoffs/watchers
    are real FK relations (one row per child); the API serializer returns them
    embedded to match the Mac client's shape."""
    CATEGORY_CHOICES = [
        ('punch',         'Punchlist'),
        ('inspection',    'Inspection'),
        ('materials',     'Materials'),
        ('office',        'Office'),
        ('subcontractor', 'Subcontractor'),
        ('other',         'Other'),
    ]
    PRIORITY_CHOICES = [
        ('low',    'Low'),
        ('normal', 'Normal'),
        ('high',   'High'),
        ('urgent', 'Urgent'),
    ]
    STATUS_CHOICES = [
        ('open',                'Open'),
        ('in_progress',         'In Progress'),
        ('blocked',             'Blocked'),
        ('needs_verification',  'Needs Verification'),
        ('done',                'Done'),
        ('wont_fix',            "Won't Fix"),
    ]
    RECURRENCE_CHOICES = [
        ('none',     'None'),
        ('daily',    'Daily'),
        ('weekly',   'Weekly'),
        ('biweekly', 'Biweekly'),
        ('monthly',  'Monthly'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')

    title    = models.CharField(max_length=255)
    details  = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')

    assigned_to      = models.ForeignKey(TeamMember, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='assigned_tasks')
    assigned_to_name = models.CharField(max_length=255, blank=True)

    due_date = models.DateField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True)

    completed_at = models.DateTimeField(blank=True, null=True)

    recurrence            = models.CharField(max_length=10, choices=RECURRENCE_CHOICES, default='none')
    reminder_days_before  = models.IntegerField(default=0)
    last_reminder_sent    = models.DateTimeField(blank=True, null=True)

    phase = models.ForeignKey(ProjectPhase, on_delete=models.SET_NULL,
                              null=True, blank=True, related_name='tasks')

    photo_filenames = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['assigned_to', 'status']),
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"


class Subtask(models.Model):
    """Checklist item under a ProjectTask. The Mac app embeds these as a JSON
    array on the parent task; we store them as FK rows but the serializer
    returns them embedded to match the Mac shape."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(ProjectTask, on_delete=models.CASCADE, related_name='subtasks')

    title        = models.CharField(max_length=255)
    is_done      = models.BooleanField(default=False)
    completed_at = models.DateTimeField(blank=True, null=True)
    due_date     = models.DateField(blank=True, null=True)
    sort_order   = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return self.title


class TaskComment(models.Model):
    """Comment on a ProjectTask. Author is a snapshot of name + optional FK
    so the comment survives if the team member is later deleted."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(ProjectTask, on_delete=models.CASCADE, related_name='comments')

    author      = models.ForeignKey(TeamMember, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='task_comments')
    author_name = models.CharField(max_length=255, blank=True)
    text        = models.TextField()
    timestamp   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.author_name}: {self.text[:60]}"


class TaskHandoff(models.Model):
    """Audit row for "I'm handing this task off to X" — append-only history.
    Mac app currently doesn't track accept/reject; we leave that for later
    rather than adding state the Mac UI doesn't surface yet."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(ProjectTask, on_delete=models.CASCADE, related_name='handoffs')

    from_member = models.ForeignKey(TeamMember, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='handoffs_sent')
    from_name   = models.CharField(max_length=255, blank=True)
    to_member   = models.ForeignKey(TeamMember, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='handoffs_received')
    to_name     = models.CharField(max_length=255, blank=True)

    note      = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.from_name} → {self.to_name}"


class TaskWatcher(models.Model):
    """Join row: which TeamMembers want notifications about a ProjectTask.
    Mac app stores this as a list of IDs on the task; we use a join table
    so the reverse query ('tasks I'm watching') is cheap."""
    task        = models.ForeignKey(ProjectTask, on_delete=models.CASCADE, related_name='watchers')
    team_member = models.ForeignKey(TeamMember, on_delete=models.CASCADE, related_name='watching_tasks')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('task', 'team_member')
        ordering = ['created_at']

    def __str__(self):
        return f"{self.team_member} watching {self.task}"


class TaskTemplate(models.Model):
    """Reusable task pattern, scoped per Company. Used to spawn ProjectTasks
    pre-populated with the template's fields + subtask titles."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='task_templates')

    name     = models.CharField(max_length=255, help_text='Template label, shown in the picker')
    title    = models.CharField(max_length=255, help_text='Default ProjectTask.title')
    details  = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=ProjectTask.CATEGORY_CHOICES, default='other')
    priority = models.CharField(max_length=10, choices=ProjectTask.PRIORITY_CHOICES, default='normal')
    location = models.CharField(max_length=255, blank=True)

    subtask_titles       = models.JSONField(default=list, blank=True, help_text='List[str] — one Subtask per title')
    recurrence           = models.CharField(max_length=10, choices=ProjectTask.RECURRENCE_CHOICES, default='none')
    reminder_days_before = models.IntegerField(default=0)

    default_assignee      = models.ForeignKey(TeamMember, on_delete=models.SET_NULL,
                                              null=True, blank=True, related_name='default_for_templates')
    default_assignee_name = models.CharField(max_length=255, blank=True)
    default_phase_name    = models.CharField(max_length=100, blank=True,
                                             help_text='Phase name (resolved per-project at spawn time)')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('company', 'name')

    def __str__(self):
        return self.name


class BudgetLineItem(models.Model):
    """CSI-coded line item under a project's budget. Different from the legacy
    Budget model's hardcoded labor/materials/etc. categories — those are kept
    as a coarse summary; this is the granular line-by-line breakdown the Mac
    app already maintains in BudgetStore (`ch_csi_line_items_v1`)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='budget_line_items')

    csi_code         = models.CharField(max_length=20, blank=True, help_text='e.g. "03 30 00"')
    csi_title        = models.CharField(max_length=255, blank=True, help_text='CSI MasterFormat title')
    description      = models.CharField(max_length=500, blank=True)
    budgeted_amount  = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sort_order       = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['project', 'sort_order', 'csi_code']
        indexes = [models.Index(fields=['project', 'csi_code'])]

    def __str__(self):
        return f"{self.csi_code} {self.description}"[:80]


class BudgetAllocation(models.Model):
    """Allocates an Invoice (or part of one) to a BudgetLineItem.
    Distinct from SubLineAllocation (A1) which allocates to subcontract lines.
    This is for general budget categorization — what the Mac BudgetStore calls
    InvoiceAllocation. A single invoice can split across multiple budget lines
    via multiple allocations."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice    = models.ForeignKey(Invoice,         on_delete=models.CASCADE, related_name='budget_allocations')
    line_item  = models.ForeignKey(BudgetLineItem,  on_delete=models.CASCADE, related_name='allocations')

    csi_code        = models.CharField(max_length=20, blank=True, help_text='Snapshot of line item CSI at allocation time')
    amount          = models.DecimalField(max_digits=14, decimal_places=2)
    allocation_date = models.DateField(default=_date.today)
    qb_pushed       = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-allocation_date', '-created_at']
        indexes = [
            models.Index(fields=['invoice']),
            models.Index(fields=['line_item']),
        ]

    def __str__(self):
        return f"${self.amount} · inv {self.invoice_id} → {self.csi_code}"


# ============================================================================
# QB Integration v2 — see QB_INTEGRATION_v2_SPEC.md
#
# QBLink: maps a ContractorHub entity to its QuickBooks counterpart, regardless
# of whether the customer uses QBO (REST) or QBWC (SOAP). One row per
# (CH entity, QB entity) pair. Replaces the scattered qb_*_id columns on
# Subcontract/Project/Invoice over time (those stay for backwards compat in v1).
# ============================================================================


class QBLink(models.Model):
    """A single mapping between a ContractorHub entity and the QB record it
    corresponds to. Used by QBService implementations to:
    - Detect "already pushed" → do an update instead of a create (idempotency)
    - Find the QB record when a follow-up event fires (e.g., when an Invoice
      moves from approved → paid, look up the Bill we already created so we
      can attach a BillPayment to it)
    - Surface per-row sync state in the Mac UI."""

    SYNC_STATE_CHOICES = [
        ('synced',           'Synced'),
        ('queued',           'Queued (waiting for QBWC poll or retry)'),
        ('failed_permanent', 'Failed permanently'),
    ]

    # Polymorphic reference: store the CH entity type as a string + ID so we
    # don't need to add a FK column for every entity that gets QB-linked.
    # (Django GenericForeignKey is overkill here; we don't need reverse lookups.)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='qb_links')

    contractorhub_entity_type = models.CharField(max_length=50,
        help_text='e.g. "Subcontract", "Project", "Invoice".')
    contractorhub_entity_id   = models.CharField(max_length=64,
        help_text='UUID or int as string — whatever the source entity uses.')

    qb_entity_type = models.CharField(max_length=50,
        help_text='e.g. "Vendor", "Customer", "Bill", "Invoice", "BillPayment".')
    qb_entity_id   = models.CharField(max_length=64, blank=True,
        help_text='Empty until first successful sync. Populated from QB response.')

    qb_sync_token = models.CharField(max_length=20, blank=True,
        help_text="QBO's optimistic-lock SyncToken; QBWC's EditSequence. Updated on every successful write.")

    sync_state     = models.CharField(max_length=20, choices=SYNC_STATE_CHOICES, default='queued')
    failure_reason = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'contractorhub_entity_type', 'contractorhub_entity_id')
        indexes = [
            models.Index(fields=['company', 'sync_state']),
            models.Index(fields=['company', 'qb_entity_type', 'qb_entity_id']),
        ]

    def __str__(self):
        return f"{self.contractorhub_entity_type}/{self.contractorhub_entity_id} → {self.qb_entity_type}/{self.qb_entity_id} [{self.sync_state}]"
