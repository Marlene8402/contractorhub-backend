"""Throttle classes for auth endpoints.

Subclasses of DRF's AnonRateThrottle so each endpoint can have its own
rate. The `scope` class attribute is what DRF uses to look up the rate
in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].

We use AnonRateThrottle (not UserRateThrottle / ScopedRateThrottle):
  - Login + register are unauthenticated, so per-IP is the only key.
  - ScopedRateThrottle relies on a `throttle_scope` view attribute that
    isn't reliably propagated through @api_view decorators.
"""
from rest_framework.throttling import AnonRateThrottle


class LoginAnonThrottle(AnonRateThrottle):
    scope = 'auth_login'


class RegisterAnonThrottle(AnonRateThrottle):
    scope = 'auth_register'
