"""Auth-endpoint rate-limit tests.

ScopedRateThrottle on /api/auth/register/ (5/min per IP) and
/api/auth/token/ (10/min per IP) defends against credential-stuffing
botnets and signup spam. These tests hammer the endpoints to confirm
the configured rate triggers a 429.
"""
from rest_framework.test import APITestCase
from django.core.cache import cache


class AuthRateLimitTests(APITestCase):
    """DRF's throttle backend uses Django's cache. Reset between tests
    so prior test runs don't bleed into the count."""

    def setUp(self):
        cache.clear()

    def test_register_throttle_kicks_in_after_5_per_min(self):
        """6th request within a minute → 429."""
        body = {
            'email': 'doesnotmatter@example.com',  # validation will fail
            'password': 'short',                    # but that's fine — we want to
            'company_name': 'X',                    # exercise the throttle, not signup
        }
        statuses = []
        for _ in range(7):
            r = self.client.post('/api/auth/register/', body, format='json')
            statuses.append(r.status_code)
        self.assertIn(429, statuses, f"Expected 429 in first 7 requests, got: {statuses}")
        self.assertGreaterEqual(statuses.count(429), 2,
            f"Expected ≥2 throttled responses (req 6 + 7), got: {statuses}")

    def test_login_throttle_kicks_in_after_10_per_min(self):
        """11th request within a minute → 429."""
        body = {'username': 'nobody@example.com', 'password': 'wrong'}
        statuses = []
        for _ in range(12):
            r = self.client.post('/api/auth/token/', body, format='json')
            statuses.append(r.status_code)
        self.assertIn(429, statuses, f"Expected 429 in first 12 requests, got: {statuses}")

    def test_register_under_limit_passes_through(self):
        """4 requests < 5/min, none should be 429."""
        body = {'email': 'a@b.c', 'password': 'short', 'company_name': 'X'}
        statuses = []
        for _ in range(4):
            r = self.client.post('/api/auth/register/', body, format='json')
            statuses.append(r.status_code)
        self.assertNotIn(429, statuses, f"Should not be throttled under limit: {statuses}")
