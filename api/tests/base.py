"""Shared test fixtures.

Every test class sets up two tenants (companies + admin users + tokens) so
cross-company isolation can be tested without per-class boilerplate. Each
tenant comes with a Project, Subcontract, and Invoice already created so
tests can focus on the entity under test.
"""
from datetime import date, timedelta
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from django.contrib.auth.models import User

from api.models import Company, TeamMember, Project, Subcontract, Invoice


class BaseAPITestCase(APITestCase):
    """Two tenants pre-baked for isolation tests."""

    @classmethod
    def setUpTestData(cls):
        cls.user1, cls.co1, cls.tm1, cls.proj1, cls.sub1, cls.inv1 = cls._make("alpha")
        cls.user2, cls.co2, cls.tm2, cls.proj2, cls.sub2, cls.inv2 = cls._make("beta")
        cls.token1 = Token.objects.create(user=cls.user1).key
        cls.token2 = Token.objects.create(user=cls.user2).key

    @staticmethod
    def _make(suffix):
        u = User.objects.create_user(
            username=f"test_{suffix}@example.com",
            email=f"test_{suffix}@example.com",
            password="x",
        )
        co = Company.objects.create(owner=u, name=f"Co {suffix}", email=u.email)
        tm = TeamMember.objects.create(
            company=co, user=u,
            first_name="Test", last_name=suffix,
            email=u.email, role="admin",
        )
        proj = Project.objects.create(
            company=co, name=f"Project {suffix}",
            client_name=f"Client {suffix}",
            contract_amount="500000.00",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=120),
            contract_number=f"CN-{suffix}-001",
        )
        sub = Subcontract.objects.create(
            project=proj, name="Concrete Package",
            vendor_name=f"Acme {suffix}",
            vendor_email=f"acme_{suffix}@example.com",
            scope="Footings + slabs",
            status="active",
        )
        inv = Invoice.objects.create(
            project=proj, invoice_number=f"INV-{suffix}-001",
            amount="10000.00",
            due_date=date.today() + timedelta(days=30),
        )
        return u, co, tm, proj, sub, inv

    def auth(self, token):
        """Set Authorization header for subsequent self.client requests."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    def auth1(self): self.auth(self.token1)
    def auth2(self): self.auth(self.token2)
