"""Tests for error-response hygiene.

Item #5 from SECURITY_FIX_LIST.md. Specifically: the IntegrityError
catch in auth_views.register used to reframe ANY DB integrity error
as 'An account with this email already exists.' That masked a real
schema-drift bug on 2026-05-01 where every signup was failing on
NOT NULL columns lacking defaults, but the user just saw 'duplicate
email'. The fix: only reframe when the constraint actually concerns
username uniqueness; everything else bubbles to a generic 500.
"""
from unittest.mock import patch

from django.db import IntegrityError
from rest_framework.test import APITestCase
from django.core.cache import cache


class IntegrityErrorReframingTests(APITestCase):
    """Confirm the catch in auth_views.register doesn't mask non-username
    integrity errors as 'duplicate email'."""

    def setUp(self):
        cache.clear()

    def _signup_body(self, email='unique-test@example.com'):
        return {
            'email': email,
            'password': 'StrongPassword2026!',
            'company_name': 'Test Co',
        }

    def test_username_uniqueness_race_returns_400_email_exists(self):
        """A username-unique-constraint IntegrityError should still surface
        as a clean 400 with 'already exists' (the legitimate race path)."""
        with patch('api.auth_views.User.objects.create_user') as mock_create:
            mock_create.side_effect = IntegrityError(
                'duplicate key value violates unique constraint '
                '"auth_user_username_key"'
            )
            r = self.client.post(
                '/api/auth/register/', self._signup_body(), format='json'
            )
            self.assertEqual(r.status_code, 400)
            self.assertIn('email', r.data)

    def test_other_integrity_error_does_not_get_reframed(self):
        """A non-username IntegrityError (NOT NULL, FK violation, etc.)
        must NOT be reframed as 'already exists'. It should bubble to a
        500 so the real bug surfaces in logs instead of misleading users."""
        # By default DRF's test client re-raises uncaught view exceptions
        # (so test stack traces are clearer). Disable that so we can
        # observe what production behavior would be — Django's default
        # 500 handler.
        self.client.raise_request_exception = False
        with patch('api.auth_views.Company.objects.create') as mock_create:
            mock_create.side_effect = IntegrityError(
                'null value in column "qb_mode" of relation "api_company" '
                'violates not-null constraint'
            )
            r = self.client.post(
                '/api/auth/register/', self._signup_body(), format='json'
            )
            # Production behavior: this becomes a 500. The key assertion
            # is that the response is NOT a 400 with the misleading
            # "already exists" payload.
            self.assertNotEqual(r.status_code, 400,
                f"Non-username IntegrityError reframed as 400 — masking real bug. "
                f"Got status {r.status_code}")
            self.assertEqual(r.status_code, 500)
