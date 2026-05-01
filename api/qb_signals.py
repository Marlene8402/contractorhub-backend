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

from datetime import date as _date
from decimal import Decimal

from .models import Invoice, Project, QBLink, Subcontract
from .qb_payloads import (
    Address, BillLine, BillPayload, BillPaymentPayload,
    CustomerJobPayload, VendorPayload,
)
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
INVOICE_WATCHED = {
    "amount", "description", "status", "kind",
    "subcontract", "vendor_invoice_number",
    "due_date", "paid_date",
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


@receiver(post_save, sender=Invoice)
def push_invoice_to_qb(sender, instance: Invoice, created: bool, update_fields=None, **kwargs):
    """Invoice saved → push as QB Bill (vendor_bill kind only) + record
    BillPayment when status flips to 'paid'.

    Client-invoice → QB Invoice flow is intentionally NOT wired here yet —
    that's Phase 4c. Triggering it now would surprise users who never
    intended their invoices to land in QB.

    Idempotency: QBLink lookup prevents creating duplicate Bills. The
    BillPayment branch only fires if a Bill QBLink exists and no
    BillPayment QBLink exists yet for this invoice.
    """
    company = instance.project.company
    if not company.qb_mode:
        return
    if instance.kind != Invoice.KIND_VENDOR_BILL:
        return
    if not _should_fire(update_fields, INVOICE_WATCHED):
        return

    try:
        svc = qb_service_for(company)

        # ----- Bill push (idempotent via QBLink) -----
        if instance.status != "draft":
            payload = _build_vendor_bill_payload(instance, company)
            if payload is None:
                # Not enough info to build the payload — already logged
                return
            result = svc.create_bill(payload)
            if result.state == "failed_permanent":
                logger.warning(
                    "QB Bill push failed permanently for Invoice %s: %s",
                    instance.id, result.failure_reason,
                )
                return  # don't try BillPayment if Bill push failed

        # ----- BillPayment push (only if status='paid' AND Bill exists in QB) -----
        if instance.status == "paid":
            bill_link = QBLink.objects.filter(
                company=company,
                contractorhub_entity_type="Invoice",
                contractorhub_entity_id=str(instance.id),
                qb_entity_type="Bill",
                sync_state="synced",
            ).first()
            payment_link = QBLink.objects.filter(
                company=company,
                contractorhub_entity_type="Invoice",
                contractorhub_entity_id=str(instance.id),
                qb_entity_type="BillPayment",
            ).first()
            if bill_link and not payment_link:
                pay_payload = _build_bill_payment_payload(instance, bill_link, company)
                if pay_payload is None:
                    return
                pay_result = svc.record_bill_payment(pay_payload)
                if pay_result.state == "failed_permanent":
                    logger.warning(
                        "QB BillPayment failed permanently for Invoice %s: %s",
                        instance.id, pay_result.failure_reason,
                    )
    except Exception:
        logger.exception("QB Invoice sync raised for Invoice %s", instance.id)


def _build_vendor_bill_payload(invoice: Invoice, company) -> "BillPayload | None":
    """Construct the BillPayload from Invoice + lookups. Returns None if
    required references aren't available (logs the reason)."""
    # 1. VendorRef — look up the Subcontract's QBLink
    if not invoice.subcontract_id:
        logger.warning(
            "Cannot push Invoice %s as Bill: no subcontract attached "
            "(vendor_bill kind requires a Subcontract reference).",
            invoice.id,
        )
        return None
    vendor_link = QBLink.objects.filter(
        company=company,
        contractorhub_entity_type="Subcontract",
        contractorhub_entity_id=str(invoice.subcontract_id),
        qb_entity_type="Vendor",
        sync_state="synced",
    ).first()
    if not vendor_link or not vendor_link.qb_entity_id:
        logger.warning(
            "Cannot push Invoice %s as Bill: Subcontract %s has no QB Vendor link yet. "
            "Save the Subcontract first to trigger vendor sync.",
            invoice.id, invoice.subcontract_id,
        )
        return None

    # 2. AccountRef — fall back to Company.default_qb_expense_account_id
    if not company.default_qb_expense_account_id:
        logger.warning(
            "Cannot push Invoice %s as Bill: Company.default_qb_expense_account_id "
            "is not set. Configure default expense GL in Settings → QuickBooks.",
            invoice.id,
        )
        return None

    # 3. Customer:Job ref (optional but preserves job-cost linkage)
    project_link = QBLink.objects.filter(
        company=company,
        contractorhub_entity_type="Project",
        contractorhub_entity_id=str(invoice.project_id),
        qb_entity_type="Customer",
        sync_state="synced",
    ).first()
    customer_job_ref = project_link.qb_entity_id if project_link else ""

    return BillPayload(
        contractorhub_id=str(invoice.id),
        vendor_qb_id=vendor_link.qb_entity_id,
        bill_date=invoice.issue_date or _date.today(),
        due_date=invoice.due_date,
        reference_number=invoice.vendor_invoice_number or "",
        memo=invoice.description or "",
        lines=[BillLine(
            description=invoice.description or invoice.invoice_number,
            amount=Decimal(invoice.amount),
            account_ref=company.default_qb_expense_account_id,
            customer_job_ref=customer_job_ref,
        )],
    )


def _build_bill_payment_payload(invoice: Invoice, bill_link, company) -> "BillPaymentPayload | None":
    """Construct the BillPaymentPayload. Returns None if required refs missing."""
    if not company.default_qb_payment_account_id:
        logger.warning(
            "Cannot push BillPayment for Invoice %s: Company.default_qb_payment_account_id "
            "is not set. Configure default payment account in Settings → QuickBooks.",
            invoice.id,
        )
        return None
    return BillPaymentPayload(
        contractorhub_id=str(invoice.id),
        bill_qb_id=bill_link.qb_entity_id,
        pay_date=invoice.paid_date or _date.today(),
        amount=Decimal(invoice.amount),
        pay_account_ref=company.default_qb_payment_account_id,
        private_note=f"Payment for {invoice.invoice_number}",
    )
