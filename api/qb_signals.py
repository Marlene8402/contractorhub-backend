"""QB Integration v2 — Django signals.

Auto-fires QB sync writes when the source CH entity is saved. Wired to:
- Subcontract (post_save)  → upsert_vendor
- Project (post_save)       → upsert_customer_job

NOT YET WIRED (deferred to Phase 4b — needs a vendor-invoice model first):
- Vendor invoice           → create_bill
- Paid vendor invoice      → record_bill_payment
- Client invoice           → create_invoice
The current Invoice model is ambiguous (no flag for vendor-bill vs
client-invoice), so wiring it now would create misdirected QB writes.

Safety rules:
1. Only fires when Company.qb_mode is set (e.g., "qbo"). DisconnectedQBService
   would no-op anyway, but we short-circuit before even constructing it to
   avoid noise.
2. Sync errors are CAUGHT inside the handler. A QB sync failure NEVER blocks
   the .save() of the underlying entity. Failed syncs surface in QBLink +
   QBSyncLog for the user to see / retry.
3. To opt out of sync on a specific .save() call (e.g., bulk imports, fixture
   loading, the sync handler updating QBLink itself), pass
   `update_fields=[...]` and ensure NONE of the fields you list are in the
   "watched" list for that signal — Django still calls post_save but the
   handler checks update_fields before firing.
"""
from __future__ import annotations

import logging
import traceback

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Project, Subcontract
from .qb_payloads import Address, CustomerJobPayload, VendorPayload
from .qb_service import qb_service_for


logger = logging.getLogger(__name__)


# Fields that, when changed, justify a re-push to QB. If a save updates ONLY
# fields outside these lists, we skip the QB call (avoids noise from
# unrelated saves like updating qb_synced flags).
SUBCONTRACT_WATCHED = {
    "vendor_name", "vendor_email", "vendor_phone",
    "is_1099_vendor", "vendor_tax_id",
    "status", "scope", "name",
}
PROJECT_WATCHED = {
    "name", "client_name", "contract_number", "contract_amount",
    "status", "start_date", "end_date",
}


def _should_fire(update_fields, watched: set[str]) -> bool:
    """Returns True if the save should trigger a QB sync.

    update_fields == None: full save → always fire
    update_fields is a set: only fire if intersection with watched is non-empty
    """
    if update_fields is None:
        return True
    return bool(set(update_fields) & watched)


@receiver(post_save, sender=Subcontract)
def push_subcontract_to_qb(sender, instance: Subcontract, created: bool, update_fields=None, **kwargs):
    """Subcontract saved → push as Vendor."""
    company = instance.project.company
    if not company.qb_mode:
        return  # not connected — DisconnectedQBService would no-op anyway
    if not _should_fire(update_fields, SUBCONTRACT_WATCHED):
        return

    try:
        svc = qb_service_for(company)
        payload = VendorPayload(
            contractorhub_id=str(instance.id),
            display_name=instance.vendor_name or instance.name,
            email=instance.vendor_email or "",
            phone=instance.vendor_phone or "",
            is_1099=bool(instance.is_1099_vendor),
            tax_id=instance.vendor_tax_id or "",
        )
        result = svc.upsert_vendor(payload)
        if result.state == "failed_permanent":
            logger.warning(
                "QB vendor sync failed permanently for Subcontract %s: %s",
                instance.id, result.failure_reason,
            )
    except Exception:
        # Never let a QB error break a save. Log + move on; QBLink/QBSyncLog
        # will reflect the failure for the user to see.
        logger.exception("QB vendor sync raised for Subcontract %s", instance.id)


@receiver(post_save, sender=Project)
def push_project_to_qb(sender, instance: Project, created: bool, update_fields=None, **kwargs):
    """Project saved → push as Customer:Job (with parent Customer for the client)."""
    company = instance.company
    if not company.qb_mode:
        return
    if not _should_fire(update_fields, PROJECT_WATCHED):
        return

    try:
        svc = qb_service_for(company)
        payload = CustomerJobPayload(
            contractorhub_id=str(instance.id),
            project_name=instance.name,
            client_name=instance.client_name,
            contract_number=instance.contract_number or "",
            contract_amount=instance.contract_amount,
            project_status=instance.status,
        )
        result = svc.upsert_customer_job(payload)
        if result.state == "failed_permanent":
            logger.warning(
                "QB customer:job sync failed permanently for Project %s: %s",
                instance.id, result.failure_reason,
            )
    except Exception:
        logger.exception("QB customer:job sync raised for Project %s", instance.id)
