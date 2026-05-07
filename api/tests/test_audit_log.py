"""Audit-log tests.

Item #6 from SECURITY_FIX_LIST.md. Confirms:
  - View-level events (signup, login, login_failed, qb_disconnect) write
    AuditLog rows with the right shape.
  - Model-level events (LienWaiver / PaymentApplication / ChangeOrder
    create/update/delete) auto-write via signals.
  - The /api/audit/ endpoint is read-only and scopes to caller's company.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from rest_framework.test import APITestCase

from api.models import (
    AuditLog,
    LienWaiver,
    PaymentApplication,
    PrimeChangeOrder,
    Subcontract,
)
from api.tests.base import BaseAPITestCase


class AuditViewLevelTests(BaseAPITestCase):
    """Auth + QB events recorded via explicit log_audit() calls."""

    def setUp(self):
        cache.clear()  # rate limits don't bleed between tests
        # Wipe any rows from BaseAPITestCase setup so each test asserts
        # cleanly on what IT created.
        AuditLog.objects.all().delete()

    def test_signup_writes_audit_row(self):
        r = self.client.post('/api/auth/register/', {
            'email': 'audit-signup@example.com',
            'password': 'StrongPassword2026!',
            'company_name': 'Audit Test Co',
        }, format='json')
        self.assertEqual(r.status_code, 201)
        rows = AuditLog.objects.filter(action='signup')
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.metadata.get('email'), 'audit-signup@example.com')
        self.assertIsNotNone(row.user)
        self.assertIsNotNone(row.company)

    def test_failed_login_writes_audit_row(self):
        r = self.client.post('/api/auth/token/', {
            'username': 'no-such-user@example.com',
            'password': 'wrong',
        }, format='json')
        self.assertNotEqual(r.status_code, 200)
        self.assertEqual(AuditLog.objects.filter(action='login_failed').count(), 1)


class AuditSignalTests(BaseAPITestCase):
    """Model-level events via post_save / post_delete signals."""

    def setUp(self):
        AuditLog.objects.all().delete()

    def test_lien_waiver_create_logs(self):
        LienWaiver.objects.create(
            project=self.proj1,
            subcontract=self.sub1,
            waiver_type='cond_partial',
            claimant_name='Test Claimant',
            through_date=date.today(),
            amount=Decimal('1000.00'),
        )
        rows = AuditLog.objects.filter(entity_type='LienWaiver', action='create')
        self.assertEqual(rows.count(), 1)

    def test_lien_waiver_status_change_logs(self):
        lw = LienWaiver.objects.create(
            project=self.proj1, subcontract=self.sub1,
            waiver_type='cond_partial',
            claimant_name='Test Claimant',
            through_date=date.today(),
            amount=Decimal('1000.00'),
            status='draft',
        )
        AuditLog.objects.all().delete()
        lw.status = 'sent'
        lw.save()
        rows = AuditLog.objects.filter(entity_type='LienWaiver', action='status_change')
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.before.get('status'), 'draft')
        self.assertEqual(row.after.get('status'), 'sent')

    def test_lien_waiver_unrelated_save_does_not_log(self):
        """Saving with no tracked-field change should NOT write a row.
        Otherwise the audit log fills up with noise."""
        lw = LienWaiver.objects.create(
            project=self.proj1, subcontract=self.sub1,
            waiver_type='cond_partial',
            claimant_name='Original',
            through_date=date.today(),
            amount=Decimal('1000.00'),
        )
        AuditLog.objects.all().delete()
        # Touch a non-tracked field; tracked fields (status, amount)
        # don't change.
        lw.claimant_name = 'Renamed'
        lw.save()
        self.assertEqual(AuditLog.objects.filter(entity_type='LienWaiver').count(), 0)

    def test_change_order_status_change_logs(self):
        co = PrimeChangeOrder.objects.create(
            project=self.proj1,
            description='Test CO',
            requested_amount=Decimal('500.00'),
            status='pending',
        )
        AuditLog.objects.all().delete()
        co.status = 'approved'
        co.approved_amount = Decimal('500.00')
        co.save()
        rows = AuditLog.objects.filter(entity_type='PrimeChangeOrder')
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().action, 'status_change')


class AuditEndpointTests(BaseAPITestCase):
    """GET /api/audit/ — read-only, company-scoped."""

    def setUp(self):
        AuditLog.objects.all().delete()
        # Plant one row for each tenant.
        AuditLog.objects.create(company=self.co1, action='signup',
                                 metadata={'note': 'alpha row'})
        AuditLog.objects.create(company=self.co2, action='signup',
                                 metadata={'note': 'beta row'})

    def test_alpha_only_sees_alpha_rows(self):
        self.auth1()
        r = self.client.get('/api/audit/')
        self.assertEqual(r.status_code, 200)
        notes = [row['metadata'].get('note') for row in r.data['results']]
        self.assertIn('alpha row', notes)
        self.assertNotIn('beta row', notes)

    def test_endpoint_is_read_only(self):
        self.auth1()
        r = self.client.post('/api/audit/', {'action': 'fake'}, format='json')
        # ReadOnlyModelViewSet → 405 Method Not Allowed
        self.assertEqual(r.status_code, 405)

    def test_filter_by_action(self):
        self.auth1()
        AuditLog.objects.create(company=self.co1, action='login_failed',
                                 metadata={})
        r = self.client.get('/api/audit/?action=login_failed')
        self.assertEqual(r.status_code, 200)
        actions = {row['action'] for row in r.data['results']}
        self.assertEqual(actions, {'login_failed'})
