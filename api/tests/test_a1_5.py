"""A1.5 endpoints: PrimeChangeOrder + SubcontractChangeOrder + OwnerContract +
PaymentApplication + PayAppLine. Includes the AIA G702 math verification."""
from datetime import date, timedelta
from .base import BaseAPITestCase


class PrimeChangeOrderTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_create_and_approved_total_action(self):
        # Two approved + one pending — only approved should sum.
        for n, amt, status_ in [("PCO-001", "10000.00", "approved"),
                                ("PCO-002", "12000.00", "approved"),
                                ("PCO-003", "5000.00",  "pending")]:
            r = self.client.post("/api/prime-change-orders/", {
                "project": self.proj1.id,
                "number": n, "title": f"CO {n}",
                "requested_amount": amt, "approved_amount": amt,
                "status": status_,
            }, format="json")
            self.assertEqual(r.status_code, 201, r.content)

        r = self.client.get(f"/api/prime-change-orders/approved_total/?project={self.proj1.id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(float(r.json()["approved_total"]), 22_000.0)


class SubcontractChangeOrderTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_create(self):
        r = self.client.post("/api/sub-change-orders/", {
            "subcontract": str(self.sub1.id),
            "number": "SCO-001", "title": "Add scope",
            "requested_amount": "5000.00", "status": "pending",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)


class OwnerContractTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_create_one_per_project(self):
        r = self.client.post("/api/owner-contracts/", {
            "project": self.proj1.id,
            "contract_number": "MASTER-001",
            "contract_type": "lump_sum",
            "signed_date": date.today().isoformat(),
            "owner_name": "Smoke Owner",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)


class PaymentApplicationG702Tests(BaseAPITestCase):
    """AIA G702/G703 math is computed in Python properties — verify the
    serializer surfaces correct totals after lines are added."""
    def setUp(self): self.auth1()

    def test_computed_totals(self):
        r = self.client.post("/api/payment-applications/", {
            "project": self.proj1.id,
            "application_number": 1,
            "application_date": date.today().isoformat(),
            "period_from": date.today().isoformat(),
            "period_to": (date.today() + timedelta(days=30)).isoformat(),
            "status": "draft",
            "retainage_percent": "10.00",
            "original_contract_sum": "500000.00",
            "net_change_orders_at_submission": "22000.00",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        pa_id = r.json()["id"]

        for item, sched, this_period, stored in [("1", "50000.00",  "20000.00", "0.00"),
                                                  ("2", "100000.00", "25000.00", "5000.00")]:
            r = self.client.post("/api/pay-app-lines/", {
                "pay_app": pa_id, "item_number": item,
                "csi_code": "01 00 00",
                "scheduled_value": sched,
                "work_completed_from_previous": "0.00",
                "work_completed_this_period": this_period,
                "materials_stored": stored,
            }, format="json")
            self.assertEqual(r.status_code, 201, r.content)

        # Re-fetch and verify G702 math:
        # contract_sum_to_date = 500_000 + 22_000 = 522_000
        # total_completed_and_stored = 20k + 30k = 50_000
        # total_retainage = 50_000 * 10% = 5_000
        # total_earned_less_retainage = 50_000 - 5_000 = 45_000
        r = self.client.get(f"/api/payment-applications/{pa_id}/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(float(body["contract_sum_to_date"]),                 522_000.0)
        self.assertEqual(float(body["total_completed_and_stored_to_date"]),    50_000.0)
        self.assertEqual(float(body["total_retainage"]),                        5_000.0)
        self.assertEqual(float(body["total_earned_less_retainage"]),           45_000.0)
