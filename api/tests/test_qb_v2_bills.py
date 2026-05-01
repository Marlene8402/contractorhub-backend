"""QB v2 — vendor-bill flow tests (Phase 4b).

Covers Invoice.kind == 'vendor_bill' signal handler:
  - Creating a vendor_bill Invoice fires create_bill (when prereqs are met)
  - Updating status='paid' fires record_bill_payment (only after Bill exists)
  - Skips when prereqs missing (no Subcontract, no Vendor link, no default GL)
  - Skips when kind='client_invoice' (Phase 4c, not wired)
  - Skips when status='draft'
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from api.models import (
    Company, Invoice, Project, QBAccount, QBLink, Subcontract, TeamMember,
)
from api.qb_payloads import SyncResult


def _make_company(suffix: str, **company_kwargs) -> Company:
    u = User.objects.create_user(username=f"qb_bill_{suffix}@x.com",
                                 email=f"qb_bill_{suffix}@x.com", password="x")
    co = Company.objects.create(
        owner=u, name=f"Co {suffix}", email=u.email,
        qb_mode="qbo",
        **company_kwargs,
    )
    TeamMember.objects.create(company=co, user=u, first_name="T", last_name=suffix,
                              email=u.email, role="admin")
    QBAccount.objects.create(
        user=u, access_token="fake-access", refresh_token="fake-refresh",
        token_expires_at=timezone.now() + timedelta(hours=2),
        realm_id="9999999999", is_connected=True,
    )
    return co


def _make_project_and_subcontract(co):
    proj = Project.objects.create(
        company=co, name="Test Project", client_name="Test Client",
        contract_number=f"CN-{co.id}", contract_amount=Decimal("100000.00"),
        start_date=date.today(), end_date=date.today() + timedelta(days=90),
    )
    return proj


# ---------------------------------------------------------------------------
# Vendor bill — happy path
# ---------------------------------------------------------------------------


class VendorBillCreateTests(APITestCase):

    @patch("api.qb_signals.qb_service_for")
    def test_vendor_bill_save_fires_create_bill_when_prereqs_met(self, mock_factory):
        co = _make_company("vb1", default_qb_expense_account_id="42")
        proj = _make_project_and_subcontract(co)

        sub = Subcontract.objects.create(project=proj, name="Concrete",
                                         vendor_name="Acme")

        # Mock initial vendor sync to set up QBLink
        mock_factory.return_value.upsert_vendor.return_value = SyncResult(
            state="synced", qb_entity_id="V100"
        )
        # Trigger the vendor sync (would normally happen on Subcontract create above,
        # but the mock_factory was attached AFTER Subcontract.create in another test
        # ordering. Ensure the QBLink exists either way:
        QBLink.objects.update_or_create(
            company=co,
            contractorhub_entity_type="Subcontract",
            contractorhub_entity_id=str(sub.id),
            defaults={
                "qb_entity_type": "Vendor", "qb_entity_id": "V100",
                "sync_state": "synced",
            },
        )

        # Now create a vendor_bill Invoice
        mock_factory.reset_mock()
        mock_factory.return_value.create_bill.return_value = SyncResult(
            state="synced", qb_entity_id="B500"
        )

        Invoice.objects.create(
            project=proj,
            invoice_number=f"BILL-001-{co.id}",
            kind=Invoice.KIND_VENDOR_BILL,
            subcontract=sub,
            vendor_invoice_number="ACME-2026-001",
            amount=Decimal("5000.00"),
            description="Footings work",
            due_date=date.today() + timedelta(days=30),
            status="sent",
        )

        mock_factory.return_value.create_bill.assert_called_once()
        payload = mock_factory.return_value.create_bill.call_args.args[0]
        self.assertEqual(payload.vendor_qb_id, "V100")
        self.assertEqual(payload.reference_number, "ACME-2026-001")
        self.assertEqual(len(payload.lines), 1)
        self.assertEqual(payload.lines[0].amount, Decimal("5000.00"))
        self.assertEqual(payload.lines[0].account_ref, "42")

    @patch("api.qb_signals.qb_service_for")
    def test_draft_vendor_bill_does_not_fire(self, mock_factory):
        co = _make_company("vb2", default_qb_expense_account_id="42")
        proj = _make_project_and_subcontract(co)
        sub = Subcontract.objects.create(project=proj, name="C", vendor_name="V")
        QBLink.objects.create(
            company=co, contractorhub_entity_type="Subcontract",
            contractorhub_entity_id=str(sub.id),
            qb_entity_type="Vendor", qb_entity_id="V100", sync_state="synced",
        )
        mock_factory.reset_mock()

        Invoice.objects.create(
            project=proj, invoice_number=f"BILL-002-{co.id}",
            kind=Invoice.KIND_VENDOR_BILL, subcontract=sub,
            amount=Decimal("100.00"),
            due_date=date.today() + timedelta(days=30),
            status="draft",  # ← stays in draft, signal should not fire create_bill
        )
        mock_factory.return_value.create_bill.assert_not_called()

    @patch("api.qb_signals.qb_service_for")
    def test_client_invoice_kind_does_not_fire_bill_handler(self, mock_factory):
        co = _make_company("vb3")
        proj = _make_project_and_subcontract(co)
        mock_factory.reset_mock()

        Invoice.objects.create(
            project=proj, invoice_number=f"INV-{co.id}",
            kind=Invoice.KIND_CLIENT_INVOICE,  # ← default kind; should be ignored by Phase 4b
            amount=Decimal("100.00"),
            due_date=date.today() + timedelta(days=30),
            status="sent",
        )
        # Phase 4b handler intentionally skips client_invoice. (Phase 4c will wire it.)
        mock_factory.return_value.create_bill.assert_not_called()
        mock_factory.return_value.create_invoice.assert_not_called()


# ---------------------------------------------------------------------------
# Vendor bill — missing prereqs
# ---------------------------------------------------------------------------


class VendorBillMissingPrereqTests(APITestCase):

    @patch("api.qb_signals.qb_service_for")
    def test_skips_when_subcontract_missing(self, mock_factory):
        co = _make_company("mp1", default_qb_expense_account_id="42")
        proj = _make_project_and_subcontract(co)
        mock_factory.reset_mock()

        Invoice.objects.create(
            project=proj, invoice_number=f"BILL-MP1-{co.id}",
            kind=Invoice.KIND_VENDOR_BILL,
            subcontract=None,  # ← missing
            amount=Decimal("100.00"),
            due_date=date.today() + timedelta(days=30),
            status="sent",
        )
        mock_factory.return_value.create_bill.assert_not_called()

    @patch("api.qb_signals.qb_service_for")
    def test_skips_when_vendor_qblink_missing(self, mock_factory):
        co = _make_company("mp2", default_qb_expense_account_id="42")
        proj = _make_project_and_subcontract(co)
        sub = Subcontract.objects.create(project=proj, name="C", vendor_name="V")
        # NO QBLink for this subcontract — vendor never synced
        mock_factory.reset_mock()

        Invoice.objects.create(
            project=proj, invoice_number=f"BILL-MP2-{co.id}",
            kind=Invoice.KIND_VENDOR_BILL, subcontract=sub,
            amount=Decimal("100.00"),
            due_date=date.today() + timedelta(days=30),
            status="sent",
        )
        mock_factory.return_value.create_bill.assert_not_called()

    @patch("api.qb_signals.qb_service_for")
    def test_skips_when_default_expense_account_unset(self, mock_factory):
        co = _make_company("mp3")  # default_qb_expense_account_id="" by default
        proj = _make_project_and_subcontract(co)
        sub = Subcontract.objects.create(project=proj, name="C", vendor_name="V")
        QBLink.objects.create(
            company=co, contractorhub_entity_type="Subcontract",
            contractorhub_entity_id=str(sub.id),
            qb_entity_type="Vendor", qb_entity_id="V100", sync_state="synced",
        )
        mock_factory.reset_mock()

        Invoice.objects.create(
            project=proj, invoice_number=f"BILL-MP3-{co.id}",
            kind=Invoice.KIND_VENDOR_BILL, subcontract=sub,
            amount=Decimal("100.00"),
            due_date=date.today() + timedelta(days=30),
            status="sent",
        )
        mock_factory.return_value.create_bill.assert_not_called()


# ---------------------------------------------------------------------------
# Bill payment — fires only after Bill exists + status='paid'
# ---------------------------------------------------------------------------


class BillPaymentTests(APITestCase):

    @patch("api.qb_signals.qb_service_for")
    def test_paid_status_fires_record_bill_payment_when_bill_link_exists(self, mock_factory):
        co = _make_company("bp1",
                           default_qb_expense_account_id="42",
                           default_qb_payment_account_id="35")
        proj = _make_project_and_subcontract(co)
        sub = Subcontract.objects.create(project=proj, name="C", vendor_name="V")
        QBLink.objects.create(
            company=co, contractorhub_entity_type="Subcontract",
            contractorhub_entity_id=str(sub.id),
            qb_entity_type="Vendor", qb_entity_id="V100", sync_state="synced",
        )
        mock_factory.return_value.create_bill.return_value = SyncResult(
            state="synced", qb_entity_id="B500"
        )
        mock_factory.return_value.record_bill_payment.return_value = SyncResult(
            state="synced", qb_entity_id="P900"
        )

        # Create Invoice in 'sent' state — fires create_bill, populates Bill QBLink
        inv = Invoice.objects.create(
            project=proj, invoice_number=f"BILL-BP1-{co.id}",
            kind=Invoice.KIND_VENDOR_BILL, subcontract=sub,
            amount=Decimal("5000.00"),
            due_date=date.today() + timedelta(days=30),
            status="sent",
        )
        # The signal handler reads QBLink to find the Bill. Since we mocked
        # qb_service_for, no QBLink was actually created by the mock.
        # Simulate the post-create_bill state:
        QBLink.objects.create(
            company=co, contractorhub_entity_type="Invoice",
            contractorhub_entity_id=str(inv.id),
            qb_entity_type="Bill", qb_entity_id="B500", sync_state="synced",
        )
        mock_factory.reset_mock()
        mock_factory.return_value.record_bill_payment.return_value = SyncResult(
            state="synced", qb_entity_id="P900"
        )

        # Now flip to paid → should fire record_bill_payment
        inv.status = "paid"
        inv.paid_date = date.today()
        inv.save()

        mock_factory.return_value.record_bill_payment.assert_called_once()
        pay_payload = mock_factory.return_value.record_bill_payment.call_args.args[0]
        self.assertEqual(pay_payload.bill_qb_id, "B500")
        self.assertEqual(pay_payload.amount, Decimal("5000.00"))
        self.assertEqual(pay_payload.pay_account_ref, "35")

    @patch("api.qb_signals.qb_service_for")
    def test_paid_status_skips_payment_when_no_bill_link(self, mock_factory):
        # status='paid' on an Invoice that never made it to QB as a Bill
        # (e.g. Bill push failed, or this is the very first save).
        co = _make_company("bp2", default_qb_expense_account_id="42",
                           default_qb_payment_account_id="35")
        proj = _make_project_and_subcontract(co)
        sub = Subcontract.objects.create(project=proj, name="C", vendor_name="V")
        QBLink.objects.create(
            company=co, contractorhub_entity_type="Subcontract",
            contractorhub_entity_id=str(sub.id),
            qb_entity_type="Vendor", qb_entity_id="V100", sync_state="synced",
        )
        mock_factory.reset_mock()
        # Bill push fails permanently (e.g., Intuit returns 400)
        mock_factory.return_value.create_bill.return_value = SyncResult(
            state="failed_permanent", failure_reason="bad data"
        )

        inv = Invoice.objects.create(
            project=proj, invoice_number=f"BILL-BP2-{co.id}",
            kind=Invoice.KIND_VENDOR_BILL, subcontract=sub,
            amount=Decimal("100.00"),
            due_date=date.today() + timedelta(days=30),
            status="paid",
            paid_date=date.today(),
        )
        # Bill push attempted but failed → no Bill QBLink → no payment attempt
        mock_factory.return_value.create_bill.assert_called_once()
        mock_factory.return_value.record_bill_payment.assert_not_called()

    @patch("api.qb_signals.qb_service_for")
    def test_paid_status_skips_payment_when_default_pay_account_unset(self, mock_factory):
        co = _make_company("bp3",
                           default_qb_expense_account_id="42")
                           # default_qb_payment_account_id NOT set
        proj = _make_project_and_subcontract(co)
        sub = Subcontract.objects.create(project=proj, name="C", vendor_name="V")
        QBLink.objects.create(
            company=co, contractorhub_entity_type="Subcontract",
            contractorhub_entity_id=str(sub.id),
            qb_entity_type="Vendor", qb_entity_id="V100", sync_state="synced",
        )
        inv = Invoice.objects.create(
            project=proj, invoice_number=f"BILL-BP3-{co.id}",
            kind=Invoice.KIND_VENDOR_BILL, subcontract=sub,
            amount=Decimal("100.00"),
            due_date=date.today() + timedelta(days=30),
            status="sent",
        )
        QBLink.objects.create(
            company=co, contractorhub_entity_type="Invoice",
            contractorhub_entity_id=str(inv.id),
            qb_entity_type="Bill", qb_entity_id="B500", sync_state="synced",
        )
        mock_factory.reset_mock()

        inv.status = "paid"
        inv.paid_date = date.today()
        inv.save()

        # Bill is re-pushed (idempotent) but payment is skipped because no pay account
        mock_factory.return_value.record_bill_payment.assert_not_called()
