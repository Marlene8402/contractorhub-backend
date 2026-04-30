"""Custom DRF permissions."""
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

from .models import Company


class SubscriptionRequired(PermissionDenied):
    """402 Payment Required — subscription expired or never started.

    DRF maps PermissionDenied subclasses to 403, so we override status_code
    to surface the billing-specific signal to the client (which can route
    the user into the upgrade flow rather than show "access denied").
    """
    status_code = 402
    default_code = 'subscription_required'

    def __init__(self, detail='Subscription required to access this resource.'):
        super().__init__(detail=detail)


class HasActiveSubscription(permissions.BasePermission):
    """Allows access only if the requesting user's company has an active
    subscription (real subscription OR active trial). Raises 402 otherwise."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        company = Company.objects.filter(owner=request.user).first()
        if not company:
            return False
        if not company.has_active_subscription:
            raise SubscriptionRequired()
        return True
