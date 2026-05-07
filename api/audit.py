"""Audit logging helpers + signal handlers.

Two entry points:

  log_audit(...)               — explicit, view-level. Captures IP + UA
                                  from request. Use for auth/QB/billing
                                  events that aren't model save/delete.

  Signal handlers (below)      — automatic. Fire on post_save / post_delete
                                  for legal-document models so any code
                                  path that mutates them is logged.

The signal handlers don't have request context, so they leave ip and
user_agent blank. Backfilling a thread-local request would be more
invasive than the value provides — for legal evidence, "user X did Y
at time T" is what matters; IP/UA is more about security ops on auth.
"""
import logging
from typing import List, Optional

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver

from .models import (
    AuditLog,
    LienWaiver,
    PaymentApplication,
    PrimeChangeOrder,
    SubcontractChangeOrder,
)

log = logging.getLogger(__name__)


# =============================================================================
# Public helper for view-level events
# =============================================================================

def log_audit(
    *,
    action: str,
    request=None,
    user=None,
    company=None,
    entity_type: str = '',
    entity_id: str = '',
    before=None,
    after=None,
    metadata: Optional[dict] = None,
) -> Optional[AuditLog]:
    """Create an AuditLog row. Never raises — logs and swallows errors so
    audit failures don't break the user-facing operation.

    All parameters are keyword-only to make call sites self-documenting.
    """
    try:
        # Pull actor + IP/UA from the request when available.
        if request is not None:
            if user is None and hasattr(request, 'user') and request.user.is_authenticated:
                user = request.user
            ip = _client_ip(request)
            ua = (request.META.get('HTTP_USER_AGENT') or '')[:1000]
        else:
            ip = None
            ua = ''

        # If no explicit company but we have a user, look up their company.
        if company is None and user is not None and user.is_authenticated:
            from .models import Company  # local import — avoid cycle
            company = Company.objects.filter(owner=user).first()

        return AuditLog.objects.create(
            company=company,
            user=user if (user and user.is_authenticated) else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else '',
            before=before,
            after=after,
            ip=ip,
            user_agent=ua,
            metadata=metadata or {},
        )
    except Exception as e:
        # Audit log failure must NEVER break the underlying operation.
        # Log to stderr and continue.
        log.warning("AuditLog.create failed: %s", e, exc_info=True)
        return None


def _client_ip(request) -> Optional[str]:
    """Best-effort caller IP. Trust X-Forwarded-For when behind Railway's
    edge — first IP in the chain is the real client."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


# =============================================================================
# Signal handlers for legal-document models
# =============================================================================
#
# We hook post_save (create + update) and post_delete on the four
# legal-grade models: LienWaiver, PaymentApplication, PrimeChangeOrder,
# SubcontractChangeOrder. For updates, we capture a status-only diff
# in metadata (full diffs would balloon the table; if you ever need
# full diffs, you can add them later via a separate "diff" field).

# Status-changing fields per model — we capture before/after of these
# specifically because they're the legally-relevant transitions.
_STATUS_FIELDS = {
    'LienWaiver':              ['status', 'amount'],
    'PaymentApplication':      ['status', 'approved_amount'],
    'PrimeChangeOrder':        ['status', 'requested_amount', 'approved_amount'],
    'SubcontractChangeOrder':  ['status', 'requested_amount', 'approved_amount'],
}


def _model_company(instance):
    """Resolve the Company a legal-doc instance belongs to. All four
    types reach Company via instance.project.company."""
    project = getattr(instance, 'project', None)
    if project is None:
        return None
    return getattr(project, 'company', None)


def _snapshot(instance, fields: List[str]) -> dict:
    """Pull a minimal field snapshot for before/after comparison."""
    out = {}
    for f in fields:
        val = getattr(instance, f, None)
        # Decimal/Date/etc → string for JSON-serialization friendliness.
        if val is not None and not isinstance(val, (str, int, float, bool, dict, list)):
            val = str(val)
        out[f] = val
    return out


@receiver(pre_save, sender=LienWaiver)
@receiver(pre_save, sender=PaymentApplication)
@receiver(pre_save, sender=PrimeChangeOrder)
@receiver(pre_save, sender=SubcontractChangeOrder)
def _stash_pre_save(sender, instance, **kwargs):
    """Stash the pre-save snapshot on the instance so post_save can
    compute a before/after diff. Only fires for updates (existing PK)."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    fields = _STATUS_FIELDS.get(sender.__name__, [])
    instance._audit_before = _snapshot(old, fields)


@receiver(post_save, sender=LienWaiver)
@receiver(post_save, sender=PaymentApplication)
@receiver(post_save, sender=PrimeChangeOrder)
@receiver(post_save, sender=SubcontractChangeOrder)
def _audit_post_save(sender, instance, created, **kwargs):
    fields = _STATUS_FIELDS.get(sender.__name__, [])
    after = _snapshot(instance, fields)
    if created:
        log_audit(
            action='create',
            company=_model_company(instance),
            entity_type=sender.__name__,
            entity_id=instance.pk,
            after=after,
        )
        return
    # Update — only log if a tracked field actually changed (avoid
    # noisy rows when an unrelated touch save happens).
    before = getattr(instance, '_audit_before', None)
    if before is None:
        return
    if before == after:
        return
    action = 'status_change' if before.get('status') != after.get('status') else 'update'
    log_audit(
        action=action,
        company=_model_company(instance),
        entity_type=sender.__name__,
        entity_id=instance.pk,
        before=before,
        after=after,
    )


@receiver(post_delete, sender=LienWaiver)
@receiver(post_delete, sender=PaymentApplication)
@receiver(post_delete, sender=PrimeChangeOrder)
@receiver(post_delete, sender=SubcontractChangeOrder)
def _audit_post_delete(sender, instance, **kwargs):
    fields = _STATUS_FIELDS.get(sender.__name__, [])
    log_audit(
        action='delete',
        company=_model_company(instance),
        entity_type=sender.__name__,
        entity_id=instance.pk,
        before=_snapshot(instance, fields),
    )
