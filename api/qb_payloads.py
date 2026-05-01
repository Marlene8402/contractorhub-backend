"""QB Integration v2 — domain payloads.

Every QB write goes through one of these dataclasses. They deliberately know
NOTHING about REST JSON or qbXML — each QBService implementation projects
them into its wire format.

This is half the patentable claim: the same payload, same call signature,
same return type, regardless of whether QBO REST or QB Desktop SOAP runs the
operation. See QB_INTEGRATION_v2_SPEC.md §2 + §9.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID


# ---------- Address (shared across vendor / customer payloads) ----------


@dataclass(frozen=True)
class Address:
    line1:  str = ""
    line2:  str = ""
    city:   str = ""
    state:  str = ""        # 2-letter US state code
    zip:    str = ""
    country: str = "US"


# ---------- Vendor (subcontractor) ----------


@dataclass
class VendorPayload:
    """A subcontractor that should exist in QB as a Vendor record."""
    contractorhub_id: str               # Subcontract.id (UUID as str) — idempotency anchor
    display_name:     str               # vendor's company / DBA name
    email:            str = ""
    phone:            str = ""
    billing_address:  Address | None = None
    is_1099:          bool = False
    tax_id:           str = ""          # EIN or SSN — required if is_1099
    terms_days:       int | None = None # net-X payment terms; None = use QB default
    notes:            str = ""


# ---------- Customer:Job (project) ----------


@dataclass
class CustomerJobPayload:
    """A project in CH that should exist in QB as a Customer:Job hierarchy.
    Per Marlene's setup (2026-04-30): client = Customer parent, project = Job child.
    """
    contractorhub_id:  str           # Project.id as str
    project_name:      str
    client_name:       str           # parent Customer's display name
    client_email:      str = ""
    client_phone:      str = ""
    client_address:    Address | None = None
    contract_number:   str = ""      # carries over to Job notes / custom field
    contract_amount:   Decimal | None = None
    project_status:    str = ""      # informational — propagates to Job notes


# ---------- Bill (sub invoice → vendor bill) ----------


@dataclass
class BillLine:
    """One line on a Bill. Either references a CH BudgetLineItem (for cost-coded
    lines) or is free-form. account_ref is the QB GL account the line posts to."""
    description:    str
    amount:         Decimal
    account_ref:    str = ""        # QB GL account ID (lookup via GL mapping)
    customer_job_ref: str = ""      # QB Customer:Job ID — links this line to a project for job-cost reporting


@dataclass
class BillPayload:
    """A sub invoice approved in CH that should appear in QB as a Bill in
    Open status. When the user later marks the CH invoice paid, we'll fire
    a separate BillPayment to flip the QB Bill to Paid."""
    contractorhub_id:  str               # Invoice.id (the CH-side sub invoice) as str
    vendor_qb_id:      str               # QB Vendor.Id — looked up via QBLink before this is built
    bill_date:         date
    due_date:          date | None = None
    reference_number:  str = ""          # vendor's invoice # if known
    memo:              str = ""
    lines:             list[BillLine] = field(default_factory=list)


# ---------- Invoice (client invoice → QB Invoice) ----------


@dataclass
class InvoiceLine:
    description:      str
    amount:           Decimal
    item_ref:         str = ""        # QB Item.Id (Service item) for revenue line
    customer_job_ref: str = ""        # the Customer:Job ID
    qty:              Decimal | None = None
    rate:             Decimal | None = None


@dataclass
class InvoicePayload:
    """A client-facing invoice that ContractorHub created and should mirror
    in QB so revenue + AR aging are correct in the books."""
    contractorhub_id:   str
    customer_qb_id:     str               # QB Customer.Id (NOT Job — root customer for the AR)
    project_qb_id:      str = ""          # QB Job.Id — for job-cost tagging on lines
    invoice_date:       date | None = None
    due_date:           date | None = None
    invoice_number:     str = ""          # CH invoice number; carries to QB DocNumber
    memo:               str = ""
    lines:              list[InvoiceLine] = field(default_factory=list)


# ---------- BillPayment (when CH invoice marked paid) ----------


@dataclass
class BillPaymentPayload:
    """Records that a Bill we previously pushed has now been paid. We look
    up the existing Bill via QBLink, then attach this payment."""
    contractorhub_id:   str               # the SAME CH Invoice.id — second event in lifecycle
    bill_qb_id:         str               # QB Bill.Id — looked up via QBLink before this is built
    pay_date:           date
    amount:             Decimal
    pay_account_ref:    str               # QB Account.Id of the bank/credit account paying
    private_note:       str = ""


# ---------- SyncResult (returned by every QBService write) ----------


@dataclass
class SyncResult:
    """Uniform return type for every QBService write — same shape whether
    QBO completed the call instantly or QBWC just queued it for the next poll.

    state semantics:
      "synced"           — operation completed at QB, qb_entity_id is populated
      "queued"           — accepted by ContractorHub, will reach QB on next poll
                           or after backoff retry. Caller treats as success-pending.
      "failed_permanent" — QB rejected with a non-retryable error
                           (validation, duplicate, invalid ref). Caller surfaces
                           failure_reason to the user.
    """
    state:           Literal["synced", "queued", "failed_permanent"]
    qb_entity_id:    str = ""
    qb_entity_type:  str = ""
    sync_log_id:     str = ""              # UUID of the QBSyncLog row, as str
    failure_reason:  str = ""
