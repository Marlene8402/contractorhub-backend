"""Lien-waiver PDF rendering tests.

Two layers:

1. Renderer functions in api.lien_waiver_pdf — given a LienWaiver, do
   they return PDF bytes that contain the verbatim statutory language
   for FL §713.20(4) and §713.20(5)?

2. The /api/lien-waivers/{id}/pdf/ endpoint — does it:
     - return a PDF for an FL waiver
     - 404 cross-tenant
     - 400 for unsupported (state, waiver_type) combos
     - audit-log the download

We extract text from the rendered PDF and grep for the required
statutory phrases. If a future code change drops or mangles the
verbatim language, these tests fail loudly.
"""
from datetime import date
from decimal import Decimal
import io

from rest_framework.test import APITestCase

from api.models import AuditLog, LienWaiver
from api.tests.base import BaseAPITestCase


def _pdf_text(pdf_bytes: bytes) -> str:
    """Extract concatenated text from PDF bytes via pypdf, with
    whitespace normalized so phrase assertions don't fail on PDF
    line-wrapping (e.g. 'waives and\\nreleases its lien' becomes
    'waives and releases its lien')."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    raw = '\n'.join(p.extract_text() or '' for p in reader.pages)
    # Collapse all runs of whitespace (including newlines) to single spaces.
    return ' '.join(raw.split())


class FLProgressFormTests(APITestCase):
    """§713.20(4) — Waiver and Release of Lien Upon Progress Payment."""

    def _waiver(self, **overrides):
        from api.models import Company, Project, Subcontract
        from django.contrib.auth.models import User
        from datetime import timedelta
        from django.utils import timezone

        u = User.objects.create_user(username='renderertest', password='x')
        co = Company.objects.create(
            owner=u, name='Renderer Test Co', email='r@x.com',
            trial_ends_at=timezone.now() + timedelta(days=30),
        )
        proj = Project.objects.create(
            company=co, name='Renderer Project',
            client_name='Acme Owner LLC',
            contract_amount='250000.00',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            contract_number='RENDER-001',
        )
        sub = Subcontract.objects.create(
            project=proj, name='Concrete', vendor_name='Big Box Concrete',
            scope='Slabs', status='active',
        )
        defaults = {
            'project': proj,
            'subcontract': sub,
            'state': 'FL',
            'waiver_type': 'uncond_partial',
            'claimant_name': 'Big Box Concrete LLC',
            'customer_name': 'Mantilla Construction',
            'owner_name': 'Acme Owner LLC',
            'job_address': '123 Main St, Miami, FL 33101',
            'through_date': date(2026, 5, 5),
            'amount': Decimal('15000.00'),
        }
        defaults.update(overrides)
        return LienWaiver.objects.create(**defaults)

    def test_renders_to_valid_pdf_bytes(self):
        from api.lien_waiver_pdf import render_pdf
        lw = self._waiver()
        buf = render_pdf(lw)
        data = buf.getvalue()
        self.assertGreater(len(data), 1000, "PDF suspiciously small")
        # Magic header — every valid PDF starts with %PDF-
        self.assertTrue(data.startswith(b'%PDF-'),
                         f"Doesn't look like a PDF: {data[:20]!r}")

    def test_contains_verbatim_statutory_title(self):
        from api.lien_waiver_pdf import render_pdf
        lw = self._waiver()
        text = _pdf_text(render_pdf(lw).getvalue())
        self.assertIn('WAIVER AND RELEASE OF LIEN UPON PROGRESS PAYMENT', text)

    def test_contains_required_statutory_phrases(self):
        """Three statutorily-required phrases from §713.20(4):
          - 'in consideration of the sum of'
          - 'waives and releases its lien'
          - 'does not cover any retention'"""
        from api.lien_waiver_pdf import render_pdf
        lw = self._waiver()
        text = _pdf_text(render_pdf(lw).getvalue())
        self.assertIn('in consideration of the sum of', text)
        self.assertIn('waives and releases its lien', text)
        self.assertIn('does not cover any retention', text)

    def test_includes_filled_in_field_values(self):
        from api.lien_waiver_pdf import render_pdf
        lw = self._waiver(amount=Decimal('15000.00'))
        text = _pdf_text(render_pdf(lw).getvalue())
        # Money formatted as $15,000.00
        self.assertIn('$15,000.00', text)
        self.assertIn('Big Box Concrete', text)
        self.assertIn('Mantilla Construction', text)
        self.assertIn('Acme Owner LLC', text)

    def test_conditional_rider_appended_when_flag_set(self):
        from api.lien_waiver_pdf import render_pdf
        lw = self._waiver(
            conditional_on_check=True,
            check_number='4711',
            check_amount=Decimal('15000.00'),
            check_date=date(2026, 5, 5),
            check_bank='Wells Fargo, N.A.',
        )
        text = _pdf_text(render_pdf(lw).getvalue())
        self.assertIn('CONDITION', text)
        self.assertIn('4711', text)
        self.assertIn('null and void', text)
        self.assertIn('Wells Fargo', text)

    def test_no_rider_when_flag_unset(self):
        from api.lien_waiver_pdf import render_pdf
        lw = self._waiver(conditional_on_check=False)
        text = _pdf_text(render_pdf(lw).getvalue())
        self.assertNotIn('null and void', text)


class FLFinalFormTests(APITestCase):
    """§713.20(5) — Waiver and Release of Lien Upon Final Payment."""

    def _waiver(self, **overrides):
        from api.models import Company, Project, Subcontract
        from django.contrib.auth.models import User
        from django.utils import timezone
        from datetime import timedelta

        u = User.objects.create_user(username='renderfinal', password='x')
        co = Company.objects.create(
            owner=u, name='Final Test Co', email='f@x.com',
            trial_ends_at=timezone.now() + timedelta(days=30),
        )
        proj = Project.objects.create(
            company=co, name='Final Project',
            client_name='Owner Inc', contract_amount='100000.00',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            contract_number='FINAL-001',
        )
        sub = Subcontract.objects.create(
            project=proj, name='Steel', vendor_name='Steel Co',
            scope='Steel', status='active',
        )
        defaults = {
            'project': proj, 'subcontract': sub,
            'state': 'FL', 'waiver_type': 'uncond_final',
            'claimant_name': 'Steel Co LLC',
            'customer_name': 'Mantilla Construction',
            'owner_name': 'Owner Inc',
            'job_address': '456 Final Ave',
            'through_date': date(2026, 6, 1),
            'amount': Decimal('25000.00'),
        }
        defaults.update(overrides)
        return LienWaiver.objects.create(**defaults)

    def test_contains_final_payment_title(self):
        from api.lien_waiver_pdf import render_pdf
        text = _pdf_text(render_pdf(self._waiver()).getvalue())
        self.assertIn('WAIVER AND RELEASE OF LIEN UPON FINAL PAYMENT', text)
        # Final form must NOT contain the progress retention disclaimer
        self.assertNotIn('does not cover any retention', text)

    def test_contains_final_payment_phrasing(self):
        from api.lien_waiver_pdf import render_pdf
        text = _pdf_text(render_pdf(self._waiver()).getvalue())
        self.assertIn('in consideration of the final payment', text)


class CAFormTests(APITestCase):
    """California §§8132 / 8134 / 8136 / 8138 — four mandatory forms.
    Tests each one renders verbatim statutory phrasing per the form."""

    def _waiver(self, **overrides):
        from api.models import Company, Project, Subcontract
        from django.contrib.auth.models import User
        from django.utils import timezone
        from datetime import timedelta

        # Pick a unique username per test using overrides as a key seed,
        # since this class generates 4 tenants (one per form variant).
        seed = overrides.get('waiver_type', 'cond_partial')
        u = User.objects.create_user(username=f'ca_{seed}', password='x')
        co = Company.objects.create(
            owner=u, name='CA Test Co', email='ca@x.com',
            trial_ends_at=timezone.now() + timedelta(days=30),
        )
        proj = Project.objects.create(
            company=co, name='SF High-Rise',
            client_name='Bay Area Properties',
            contract_amount='1000000.00',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            contract_number=f'CA-{seed}',
        )
        sub = Subcontract.objects.create(
            project=proj, name='Drywall',
            vendor_name='West Coast Drywall', scope='Drywall',
            status='active',
        )
        defaults = {
            'project': proj, 'subcontract': sub,
            'state': 'CA',
            'waiver_type': 'cond_partial',
            'claimant_name': 'West Coast Drywall, Inc.',
            'customer_name': 'GC General Contractors',
            'owner_name': 'Bay Area Properties LLC',
            'job_address': '500 Mission St, San Francisco, CA 94105',
            'through_date': date(2026, 5, 5),
            'amount': Decimal('25000.00'),
            'check_number': '4711',
            'check_amount': Decimal('25000.00'),
            'check_date': date(2026, 5, 5),
            'check_bank': 'Bank of the West',
        }
        defaults.update(overrides)
        return LienWaiver.objects.create(**defaults)

    # §8132 — Conditional Progress
    def test_8132_title_and_notice(self):
        from api.lien_waiver_pdf import render_pdf
        text = _pdf_text(render_pdf(self._waiver(waiver_type='cond_partial')).getvalue())
        self.assertIn('CONDITIONAL WAIVER AND RELEASE ON PROGRESS PAYMENT', text)
        self.assertIn('EFFECTIVE ON RECEIPT OF PAYMENT', text)
        self.assertIn('SHOULD NOT RELY', text)

    def test_8132_includes_through_date_and_check_block(self):
        from api.lien_waiver_pdf import render_pdf
        text = _pdf_text(render_pdf(self._waiver(waiver_type='cond_partial')).getvalue())
        self.assertIn('Through Date', text)
        self.assertIn('Maker of Check', text)
        self.assertIn('Bank of the West', text)
        # Must include all four §8132 exception items
        self.assertIn('Retentions', text)
        self.assertIn('Extras', text)
        self.assertIn('previously given a conditional waiver', text)
        self.assertIn('rescission', text)

    # §8134 — Unconditional Progress
    def test_8134_title_and_warning_notice(self):
        from api.lien_waiver_pdf import render_pdf
        text = _pdf_text(render_pdf(self._waiver(waiver_type='uncond_partial')).getvalue())
        self.assertIn('UNCONDITIONAL WAIVER AND RELEASE ON PROGRESS PAYMENT', text)
        self.assertIn('NOTICE TO CLAIMANT', text)
        self.assertIn('ENFORCEABLE AGAINST YOU IF YOU SIGN IT', text)
        self.assertIn('USE A CONDITIONAL WAIVER AND RELEASE FORM', text)

    def test_8134_states_payment_received(self):
        from api.lien_waiver_pdf import render_pdf
        text = _pdf_text(render_pdf(self._waiver(waiver_type='uncond_partial')).getvalue())
        self.assertIn('claimant has received the following progress payment', text)
        self.assertIn('$25,000.00', text)
        # No check block on unconditional forms
        self.assertNotIn('Maker of Check', text)
        # 3 exceptions on §8134, NOT 4 (no "previously conditional" item)
        self.assertNotIn('previously given a conditional waiver', text)

    # §8136 — Conditional Final
    def test_8136_title_no_through_date(self):
        from api.lien_waiver_pdf import render_pdf
        text = _pdf_text(render_pdf(self._waiver(waiver_type='cond_final')).getvalue())
        self.assertIn('CONDITIONAL WAIVER AND RELEASE ON FINAL PAYMENT', text)
        # Final forms omit Through Date in identifying info
        self.assertNotIn('Through Date', text)

    def test_8136_change_order_clause_and_disputed_extras(self):
        from api.lien_waiver_pdf import render_pdf
        text = _pdf_text(render_pdf(self._waiver(waiver_type='cond_final')).getvalue())
        # The change-order language is unique to final forms
        self.assertIn('written change order', text)
        # Final forms have a single exception, not a 4-item list
        self.assertIn('Disputed claims for extras', text)

    # §8138 — Unconditional Final
    def test_8138_title_and_paid_in_full(self):
        from api.lien_waiver_pdf import render_pdf
        text = _pdf_text(render_pdf(self._waiver(waiver_type='uncond_final')).getvalue())
        self.assertIn('UNCONDITIONAL WAIVER AND RELEASE ON FINAL PAYMENT', text)
        self.assertIn('claimant has been paid in full', text)
        self.assertIn('NOTICE TO CLAIMANT', text)


class LienWaiverPdfEndpointTests(BaseAPITestCase):
    """The /api/lien-waivers/{id}/pdf/ download endpoint."""

    def setUp(self):
        AuditLog.objects.all().delete()

    def _make_fl_waiver(self, project, sub):
        return LienWaiver.objects.create(
            project=project, subcontract=sub,
            state='FL', waiver_type='uncond_partial',
            claimant_name='Endpoint Test',
            customer_name='Customer', owner_name='Owner',
            through_date=date(2026, 5, 5),
            amount=Decimal('1000.00'),
        )

    def test_pdf_endpoint_returns_pdf(self):
        lw = self._make_fl_waiver(self.proj1, self.sub1)
        self.auth1()
        r = self.client.get(f'/api/lien-waivers/{lw.id}/pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF-'))

    def test_pdf_endpoint_cross_tenant_404(self):
        """User alpha cannot download User beta's waiver."""
        lw = self._make_fl_waiver(self.proj2, self.sub2)
        self.auth1()
        r = self.client.get(f'/api/lien-waivers/{lw.id}/pdf/')
        self.assertEqual(r.status_code, 404)

    def test_pdf_endpoint_400_for_unsupported_state(self):
        lw = self._make_fl_waiver(self.proj1, self.sub1)
        lw.state = 'TX'  # not supported yet (FL + CA are; TX/NY pending)
        lw.save(update_fields=['state'])
        self.auth1()
        r = self.client.get(f'/api/lien-waivers/{lw.id}/pdf/')
        self.assertEqual(r.status_code, 400)

    def test_pdf_endpoint_writes_audit_row(self):
        lw = self._make_fl_waiver(self.proj1, self.sub1)
        self.auth1()
        self.client.get(f'/api/lien-waivers/{lw.id}/pdf/')
        rows = AuditLog.objects.filter(
            entity_type='LienWaiver', entity_id=str(lw.id),
        )
        # There's also a 'create' row from when LienWaiver was made; we
        # care that an additional 'update' row landed for the download.
        download_rows = [r for r in rows if r.metadata.get('pdf_downloaded')]
        self.assertEqual(len(download_rows), 1)
