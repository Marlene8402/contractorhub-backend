"""A1 endpoints: subcontracts + line items + allocations, COIs, daily logs,
lien waivers. Mirrors the relevant scenarios from /tmp/prod_crud_smoke.py."""
from datetime import date, timedelta
from .base import BaseAPITestCase


class SubcontractTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_create_with_line_items_and_computed_total(self):
        # Two line items → contract_amount should sum to their amounts.
        for amt, desc, order in [("25000.00", "Footings", 1),
                                 ("75000.00", "Walls",    2)]:
            r = self.client.post("/api/subcontract-line-items/", {
                "subcontract": str(self.sub1.id),
                "csi_code": "03 30 00", "csi_title": "Cast-in-Place",
                "description": desc, "amount": amt, "sort_order": order,
            }, format="json")
            self.assertEqual(r.status_code, 201, r.content)

        r = self.client.get(f"/api/subcontracts/{self.sub1.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(float(r.json()["contract_amount"]), 100_000.0)

    def test_patch_updates_status(self):
        r = self.client.patch(f"/api/subcontracts/{self.sub1.id}/",
                              {"status": "completed"}, format="json")
        self.assertEqual(r.status_code, 200)
        r = self.client.get(f"/api/subcontracts/{self.sub1.id}/")
        self.assertEqual(r.json()["status"], "completed")


class InsuranceCertificateTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_computed_status_and_days_until_expiration(self):
        future = (date.today() + timedelta(days=400)).isoformat()
        r = self.client.post("/api/insurance-certificates/", {
            "subcontract": str(self.sub1.id),
            "coverage_type": "general_liability",
            "carrier": "Hartford", "policy_number": "GL-12345",
            "effective_date": date.today().isoformat(),
            "expiration_date": future,
            "coverage_limit": "2000000.00",
            "additional_insured": True,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["status"], "active")
        self.assertIn(r.json()["days_until_expiration"], (399, 400))

    def test_computed_status_when_expired(self):
        past = (date.today() - timedelta(days=10)).isoformat()
        r = self.client.post("/api/insurance-certificates/", {
            "subcontract": str(self.sub1.id),
            "coverage_type": "workers_comp",
            "expiration_date": past,
            "effective_date": (date.today() - timedelta(days=400)).isoformat(),
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["status"], "expired")


class DailyLogTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_create_with_photos_json(self):
        r = self.client.post("/api/daily-logs/", {
            "project": self.proj1.id,
            "log_date": date.today().isoformat(),
            "weather": "Sunny, 72°F", "crew_size": 8,
            "work_performed": "Footings",
            "photo_filenames": ["IMG_001.jpg", "IMG_002.jpg"],
            "author_name": "Test",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["photo_filenames"], ["IMG_001.jpg", "IMG_002.jpg"])


class LienWaiverTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_create_conditional_partial(self):
        r = self.client.post("/api/lien-waivers/", {
            "project": self.proj1.id, "subcontract": str(self.sub1.id),
            "waiver_type": "cond_partial", "status": "draft",
            "claimant_name": "Acme Concrete",
            "customer_name": "GC",
            "owner_name": "Owner LLC",
            "through_date": date.today().isoformat(),
            "amount": "5000.00",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["waiver_type"], "cond_partial")


class A1TenantIsolationTests(BaseAPITestCase):
    """Co2 must not see Co1's A1 entities."""

    def test_subcontracts_isolated(self):
        self.auth2()
        r = self.client.get("/api/subcontracts/")
        self.assertEqual(r.status_code, 200)
        ids = [s["id"] for s in r.json()["results"]]
        self.assertIn(str(self.sub2.id), ids)
        self.assertNotIn(str(self.sub1.id), ids)

    def test_subcontract_detail_404_across_tenant(self):
        self.auth2()
        r = self.client.get(f"/api/subcontracts/{self.sub1.id}/")
        self.assertEqual(r.status_code, 404)
