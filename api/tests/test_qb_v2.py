"""QB Integration v2 — unit tests using mocked Intuit responses.

Covers what doesn't need the real Intuit sandbox:
- The abstraction (QBService factory dispatch + DisconnectedQBService)
- QBOService body builders → correct Intuit JSON shape
- QBOService error classification (4xx → permanent, 5xx → transient)
- QBOService idempotency routing (existing QBLink → update body shape)
- Signals fire on Subcontract/Project save when qb_mode='qbo'
- Signals short-circuit when qb_mode is empty
- update_fields filtering (skip noisy saves)

Live-against-sandbox verification of vendor create + idempotent update is
already documented in commit d999937. The chain test (Subcontract.save()
fires signal → real Intuit Vendor created) runs as a separate manual smoke
script; it can't be in the test suite because it hits the network.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import responses
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from api.models import (
    Company, Project, QBAccount, QBLink, QBSyncLog, Subcontract, TeamMember,
)
from api.qb_payloads import Address, CustomerJobPayload, SyncResult, VendorPayload
from api.qb_qbo import QBOService, QBOPermanentError, QBOTransientError
from api.qb_service import DisconnectedQBService, QBService, qb_service_for


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_company(suffix: str, qb_mode: str = "") -> Company:
    u = User.objects.create_user(username=f"qb_test_{suffix}@x.com",
                                 email=f"qb_test_{suffix}@x.com", password="x")
    co = Company.objects.create(owner=u, name=f"Co {suffix}", email=u.email,
                                qb_mode=qb_mode)
    TeamMember.objects.create(company=co, user=u, first_name="T", last_name=suffix,
                              email=u.email, role="admin")
    if qb_mode == "qbo":
        QBAccount.objects.create(
            user=u, access_token="fake-access", refresh_token="fake-refresh",
            token_expires_at=timezone.now() + timedelta(hours=2),
            realm_id="9999999999", is_connected=True,
        )
    return co


def _make_project(co: Company, name: str = "Bayside") -> Project:
    return Project.objects.create(
        company=co, name=name, client_name="Coastal Hospitality",
        contract_number=f"CN-{name}", contract_amount=Decimal("385000.00"),
        start_date=date.today(), end_date=date.today() + timedelta(days=180),
    )


# ---------------------------------------------------------------------------
# Factory dispatch
# ---------------------------------------------------------------------------


class FactoryDispatchTests(APITestCase):
    """qb_service_for() returns the right implementation based on Company.qb_mode."""

    def test_disconnected_when_mode_empty(self):
        co = _make_company("d1", qb_mode="")
        svc = qb_service_for(co)
        self.assertIsInstance(svc, DisconnectedQBService)

    def test_qbo_when_mode_qbo(self):
        co = _make_company("d2", qb_mode="qbo")
        svc = qb_service_for(co)
        self.assertIsInstance(svc, QBOService)


# ---------------------------------------------------------------------------
# DisconnectedQBService — safe no-op
# ---------------------------------------------------------------------------


class DisconnectedServiceTests(APITestCase):
    """Calling any write on the disconnected service returns failed_permanent
    without raising. Reads return empty lists."""

    def setUp(self):
        self.co = _make_company("dq")
        self.svc = qb_service_for(self.co)

    def test_is_connected_returns_disconnected_state(self):
        self.assertEqual(self.svc.is_connected().state, "disconnected")

    def test_reads_return_empty(self):
        self.assertEqual(self.svc.list_vendors(), [])
        self.assertEqual(self.svc.list_customers(), [])
        self.assertEqual(self.svc.list_chart_of_accounts(), [])
        self.assertEqual(self.svc.list_items(), [])

    def test_writes_return_failed_permanent_with_clear_reason(self):
        for r in [
            self.svc.upsert_vendor(VendorPayload(contractorhub_id="x", display_name="x")),
            self.svc.upsert_customer_job(CustomerJobPayload(
                contractorhub_id="x", project_name="x", client_name="x")),
        ]:
            self.assertEqual(r.state, "failed_permanent")
            self.assertIn("Not connected", r.failure_reason)


# ---------------------------------------------------------------------------
# QBOService.upsert_vendor — body shapes (mocked Intuit)
# ---------------------------------------------------------------------------


class QBOVendorBodyTests(APITestCase):
    """Verify the JSON body QBOService POSTs to /vendor matches what Intuit expects."""

    def setUp(self):
        self.co = _make_company("v", qb_mode="qbo")
        self.svc = QBOService(self.co)

    @responses.activate
    def test_create_vendor_body_shape(self):
        captured = {}
        def _record(request):
            import json as _json
            captured["body"]    = _json.loads(request.body)
            captured["headers"] = dict(request.headers)
            return (201, {}, _json.dumps({
                "Vendor": {"Id": "777", "SyncToken": "0", "DisplayName": "Acme"}
            }))

        responses.add_callback(
            responses.POST,
            "https://sandbox-quickbooks.api.intuit.com/v3/company/9999999999/vendor",
            callback=_record,
        )

        result = self.svc.upsert_vendor(VendorPayload(
            contractorhub_id="sub-uuid-abc",
            display_name="Acme Concrete",
            email="ops@acme.example",
            phone="555-1234",
            is_1099=True,
            tax_id="12-3456789",
            terms_days=30,
            billing_address=Address(line1="123 Main", city="Austin",
                                    state="TX", zip="78701"),
        ))

        self.assertEqual(result.state, "synced")
        self.assertEqual(result.qb_entity_id, "777")
        self.assertEqual(result.qb_entity_type, "Vendor")

        body = captured["body"]
        self.assertEqual(body["DisplayName"],            "Acme Concrete")
        self.assertEqual(body["Vendor1099"],             True)
        self.assertEqual(body["TaxIdentifier"],          "12-3456789")
        self.assertEqual(body["PrimaryEmailAddr"],       {"Address": "ops@acme.example"})
        self.assertEqual(body["PrimaryPhone"],           {"FreeFormNumber": "555-1234"})
        self.assertEqual(body["BillAddr"]["Line1"],      "123 Main")
        self.assertEqual(body["BillAddr"]["CountrySubDivisionCode"], "TX")
        # No Id present — this is a create, not an update
        self.assertNotIn("Id", body)
        self.assertNotIn("SyncToken", body)
        self.assertNotIn("sparse", body)

        # Auth header present
        self.assertEqual(captured["headers"]["Authorization"], "Bearer fake-access")
        # Idempotency header is deterministic on (CH id, qb_entity_type)
        self.assertEqual(
            captured["headers"]["Idempotency-Key"],
            "ch-subcontract-sub-uuid-abc-vendor",
        )

    @responses.activate
    def test_update_vendor_body_includes_id_synctoken_sparse(self):
        # Pre-seed a QBLink so the second call routes as update, not create
        QBLink.objects.create(
            company=self.co,
            contractorhub_entity_type="Subcontract",
            contractorhub_entity_id="sub-uuid-existing",
            qb_entity_type="Vendor",
            qb_entity_id="42",
            qb_sync_token="3",
            sync_state="synced",
        )

        captured = {}
        def _record(request):
            import json as _json
            captured["body"] = _json.loads(request.body)
            return (200, {}, _json.dumps({
                "Vendor": {"Id": "42", "SyncToken": "4", "DisplayName": "Acme v2"}
            }))

        responses.add_callback(
            responses.POST,
            "https://sandbox-quickbooks.api.intuit.com/v3/company/9999999999/vendor",
            callback=_record,
        )

        result = self.svc.upsert_vendor(VendorPayload(
            contractorhub_id="sub-uuid-existing",
            display_name="Acme v2",
        ))

        self.assertEqual(result.state, "synced")
        self.assertEqual(result.qb_entity_id, "42")  # SAME — update, not create

        body = captured["body"]
        self.assertEqual(body["Id"],         "42")
        self.assertEqual(body["SyncToken"],  "3")
        self.assertEqual(body["sparse"],     True)

        # QBLink updated with new SyncToken
        link = QBLink.objects.get(contractorhub_entity_id="sub-uuid-existing")
        self.assertEqual(link.qb_sync_token, "4")
        self.assertEqual(link.sync_state, "synced")


# ---------------------------------------------------------------------------
# QBOService error classification
# ---------------------------------------------------------------------------


class QBOErrorClassificationTests(APITestCase):
    def setUp(self):
        self.co = _make_company("err", qb_mode="qbo")
        self.svc = QBOService(self.co)

    @responses.activate
    def test_400_returns_failed_permanent(self):
        responses.add(
            responses.POST,
            "https://sandbox-quickbooks.api.intuit.com/v3/company/9999999999/vendor",
            json={"Fault": {"Error": [{"Message": "DisplayName required",
                                       "Detail": "Empty value"}]}},
            status=400,
        )
        result = self.svc.upsert_vendor(VendorPayload(
            contractorhub_id="x", display_name="Doomed",
        ))
        self.assertEqual(result.state, "failed_permanent")
        self.assertIn("DisplayName required", result.failure_reason)

        link = QBLink.objects.get(contractorhub_entity_id="x")
        self.assertEqual(link.sync_state, "failed_permanent")

    @responses.activate
    def test_500_returns_queued(self):
        responses.add(
            responses.POST,
            "https://sandbox-quickbooks.api.intuit.com/v3/company/9999999999/vendor",
            body="Internal Server Error",
            status=500,
        )
        result = self.svc.upsert_vendor(VendorPayload(
            contractorhub_id="y", display_name="Transient",
        ))
        self.assertEqual(result.state, "queued")

        link = QBLink.objects.get(contractorhub_entity_id="y")
        self.assertEqual(link.sync_state, "queued")

    @responses.activate
    def test_401_returns_failed_permanent_token_problem(self):
        # 401 is classified as PermanentError — caller should re-auth
        responses.add(
            responses.POST,
            "https://sandbox-quickbooks.api.intuit.com/v3/company/9999999999/vendor",
            json={"Fault": {"Error": [{"Message": "Authentication required"}]}},
            status=401,
        )
        result = self.svc.upsert_vendor(VendorPayload(
            contractorhub_id="z", display_name="x",
        ))
        self.assertEqual(result.state, "failed_permanent")


# ---------------------------------------------------------------------------
# Signals — fire on save when qb_mode='qbo', skip otherwise
# ---------------------------------------------------------------------------


class SignalDispatchTests(APITestCase):

    @patch("api.qb_signals.qb_service_for")
    def test_subcontract_save_fires_signal_when_qbo_connected(self, mock_factory):
        co = _make_company("s1", qb_mode="qbo")
        proj = _make_project(co)

        mock_svc = mock_factory.return_value
        mock_svc.upsert_vendor.return_value = SyncResult(state="synced", qb_entity_id="100")

        Subcontract.objects.create(
            project=proj, name="Concrete", vendor_name="Acme Concrete",
            vendor_email="ops@acme.example", scope="Footings",
        )

        mock_svc.upsert_vendor.assert_called_once()
        payload = mock_svc.upsert_vendor.call_args.args[0]
        self.assertEqual(payload.display_name, "Acme Concrete")
        self.assertEqual(payload.email, "ops@acme.example")

    @patch("api.qb_signals.qb_service_for")
    def test_subcontract_save_skips_signal_when_disconnected(self, mock_factory):
        co = _make_company("s2", qb_mode="")
        proj = _make_project(co)

        Subcontract.objects.create(
            project=proj, name="Concrete", vendor_name="Acme",
        )

        mock_factory.assert_not_called()

    @patch("api.qb_signals.qb_service_for")
    def test_project_save_fires_signal_when_qbo_connected(self, mock_factory):
        co = _make_company("s3", qb_mode="qbo")
        mock_svc = mock_factory.return_value
        mock_svc.upsert_customer_job.return_value = SyncResult(state="synced", qb_entity_id="200")

        _make_project(co, name="Hilltop")

        mock_svc.upsert_customer_job.assert_called_once()
        payload = mock_svc.upsert_customer_job.call_args.args[0]
        self.assertEqual(payload.project_name, "Hilltop")
        self.assertEqual(payload.client_name, "Coastal Hospitality")

    @patch("api.qb_signals.qb_service_for")
    def test_subcontract_save_with_unrelated_update_fields_skipped(self, mock_factory):
        co = _make_company("s4", qb_mode="qbo")
        proj = _make_project(co)
        sub = Subcontract.objects.create(
            project=proj, name="C", vendor_name="A",
        )
        # Reset the mock — the create above fired one call we don't care about
        mock_factory.reset_mock()

        # Save with update_fields that doesn't intersect SUBCONTRACT_WATCHED:
        # `updated_at` is auto-only, but explicitly listing only that
        # exercises the _should_fire filter.
        sub.save(update_fields=["updated_at"])

        # Signal handler short-circuits — factory never called
        mock_factory.assert_not_called()

    @patch("api.qb_signals.qb_service_for")
    def test_subcontract_save_with_watched_update_fields_fires(self, mock_factory):
        co = _make_company("s5", qb_mode="qbo")
        proj = _make_project(co)
        sub = Subcontract.objects.create(project=proj, name="C", vendor_name="A")
        mock_factory.reset_mock()
        mock_factory.return_value.upsert_vendor.return_value = SyncResult(
            state="synced", qb_entity_id="x"
        )

        sub.vendor_phone = "555-1234"
        sub.save(update_fields=["vendor_phone"])

        mock_factory.return_value.upsert_vendor.assert_called_once()

    @patch("api.qb_signals.qb_service_for")
    def test_signal_handler_swallows_qb_failure(self, mock_factory):
        co = _make_company("s6", qb_mode="qbo")
        proj = _make_project(co)
        # QB sync raises an unexpected error
        mock_factory.return_value.upsert_vendor.side_effect = RuntimeError("boom")

        # Save should still succeed — signal handler must not propagate
        sub = Subcontract.objects.create(project=proj, name="C", vendor_name="A")
        self.assertIsNotNone(sub.id)
