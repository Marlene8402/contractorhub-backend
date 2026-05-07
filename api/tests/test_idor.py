"""Cross-tenant IDOR tests.

Two tenants are pre-baked by BaseAPITestCase. These tests probe whether
User A (alpha) can plant or modify data on User B's (beta) projects via
direct API calls, by passing B's project/subcontract/task IDs in POST
bodies. The READ side is already scoped via _CompanyScopedViewSet; the
WRITE side is what these tests exercise.

If any of these tests pass on a clean run before the IDOR fix lands,
that confirms the bug. After the fix, all should pass.
"""
from rest_framework import status

from api.models import (
    Subcontract, ProjectTask, DailyLog, LienWaiver, ScheduleItem,
    PrimeChangeOrder, PaymentApplication,
)
from api.tests.base import BaseAPITestCase


class IDORWriteTests(BaseAPITestCase):
    """User A POSTing with User B's project/parent FK should be rejected
    (403 PermissionDenied or 400 with a validation error). It must NOT
    succeed and create a row owned (transitively) by B's company."""

    def test_subcontract_cross_tenant_create_blocked(self):
        """User alpha cannot create a Subcontract on Beta's project."""
        self.auth1()
        before = Subcontract.objects.filter(project=self.proj2).count()
        r = self.client.post('/api/subcontracts/', {
            'project': self.proj2.id,        # Beta's project
            'name': 'IDOR PROBE',
            'vendor_name': 'Attacker',
            'scope': 'Should not exist',
            'status': 'active',
        }, format='json')
        self.assertNotEqual(r.status_code, 201, f"IDOR! Created sub on cross-tenant project: {r.data}")
        self.assertEqual(
            Subcontract.objects.filter(project=self.proj2).count(), before,
            "Beta's project gained a subcontract from Alpha — IDOR confirmed",
        )

    def test_project_task_cross_tenant_create_blocked(self):
        """User alpha cannot create a ProjectTask on Beta's project."""
        self.auth1()
        before = ProjectTask.objects.filter(project=self.proj2).count()
        r = self.client.post('/api/project-tasks/', {
            'project': self.proj2.id,
            'title': 'IDOR PROBE',
            'category': 'other',
            'priority': 'normal',
            'status': 'open',
            'recurrence': 'none',
            'reminder_days_before': 0,
            'photo_filenames': [],
        }, format='json')
        self.assertNotEqual(r.status_code, 201, f"IDOR! {r.data}")
        self.assertEqual(ProjectTask.objects.filter(project=self.proj2).count(), before)

    def test_daily_log_cross_tenant_create_blocked(self):
        self.auth1()
        before = DailyLog.objects.filter(project=self.proj2).count()
        r = self.client.post('/api/daily-logs/', {
            'project': self.proj2.id,
            'log_date': '2026-05-05',
            'weather': 'sunny',
            'crew_size': 1,
            'work_performed': 'IDOR probe',
        }, format='json')
        self.assertNotEqual(r.status_code, 201, f"IDOR! {r.data}")
        self.assertEqual(DailyLog.objects.filter(project=self.proj2).count(), before)

    def test_schedule_item_cross_tenant_create_blocked(self):
        self.auth1()
        before = ScheduleItem.objects.filter(project=self.proj2).count()
        r = self.client.post('/api/schedule-items/', {
            'project': self.proj2.id,
            'kind': 'task',
            'title': 'IDOR PROBE',
            'start_date': '2026-05-05',
            'end_date': '2026-05-06',
        }, format='json')
        self.assertNotEqual(r.status_code, 201, f"IDOR! {r.data}")
        self.assertEqual(ScheduleItem.objects.filter(project=self.proj2).count(), before)

    def test_lien_waiver_cross_tenant_create_blocked(self):
        self.auth1()
        before = LienWaiver.objects.filter(project=self.proj2).count()
        r = self.client.post('/api/lien-waivers/', {
            'project': self.proj2.id,
            'subcontract': self.sub2.id,     # Beta's sub
            'kind': 'progress',
            'claimant_name': 'Attacker',
            'amount': '1.00',
        }, format='json')
        self.assertNotEqual(r.status_code, 201, f"IDOR! {r.data}")
        self.assertEqual(LienWaiver.objects.filter(project=self.proj2).count(), before)

    def test_prime_change_order_cross_tenant_create_blocked(self):
        self.auth1()
        before = PrimeChangeOrder.objects.filter(project=self.proj2).count()
        r = self.client.post('/api/prime-change-orders/', {
            'project': self.proj2.id,
            'co_number': 'CO-IDOR',
            'description': 'IDOR probe',
            'amount': '1.00',
        }, format='json')
        self.assertNotEqual(r.status_code, 201, f"IDOR! {r.data}")
        self.assertEqual(PrimeChangeOrder.objects.filter(project=self.proj2).count(), before)

    def test_payment_application_cross_tenant_create_blocked(self):
        self.auth1()
        before = PaymentApplication.objects.filter(project=self.proj2).count()
        r = self.client.post('/api/payment-applications/', {
            'project': self.proj2.id,
            'pay_app_number': 99,
            'period_start': '2026-05-01',
            'period_end': '2026-05-31',
        }, format='json')
        self.assertNotEqual(r.status_code, 201, f"IDOR! {r.data}")
        self.assertEqual(PaymentApplication.objects.filter(project=self.proj2).count(), before)


class IDORReadTests(BaseAPITestCase):
    """Read-side scoping should already be solid via _CompanyScopedViewSet.
    These tests verify it stays that way."""

    def test_subcontract_detail_cross_tenant_404(self):
        """User alpha GETting Beta's subcontract by UUID should 404."""
        self.auth1()
        r = self.client.get(f'/api/subcontracts/{self.sub2.id}/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_project_detail_cross_tenant_404(self):
        self.auth1()
        r = self.client.get(f'/api/projects/{self.proj2.id}/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_subcontract_list_filtered_by_company(self):
        """User alpha listing /api/subcontracts/ should NOT see Beta's."""
        self.auth1()
        r = self.client.get('/api/subcontracts/')
        self.assertEqual(r.status_code, 200)
        ids = [item['id'] for item in r.data['results']]
        self.assertIn(str(self.sub1.id), ids)
        self.assertNotIn(str(self.sub2.id), ids)
