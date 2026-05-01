"""Stripe billing endpoints — checkout + customer portal.

The webhook handler lives in webhook_views.py (no auth, signature-verified).
"""
import stripe
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Company


# Tier name -> settings attribute holding the Stripe price ID.
_PRICE_BY_TIER = {
    Company.TIER_STARTER: 'STRIPE_PRICE_STARTER',
    Company.TIER_PRO:     'STRIPE_PRICE_PRO',
    Company.TIER_SCALE:   'STRIPE_PRICE_SCALE',
}


def _company(user):
    return Company.objects.filter(owner=user).first()


def _require_stripe():
    if not settings.STRIPE_SECRET_KEY:
        return Response(
            {'detail': 'Stripe is not configured on this server.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return None


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_checkout_session(request):
    """Create a Stripe Checkout session for the requested tier.
    POST body: {"tier": "starter" | "pro" | "scale"}
    Response: {"url": "...", "session_id": "..."}"""
    err = _require_stripe()
    if err:
        return err

    tier = (request.data.get('tier') or '').lower()
    if tier not in _PRICE_BY_TIER:
        return Response(
            {'tier': [f'Must be one of: {", ".join(_PRICE_BY_TIER)}']},
            status=status.HTTP_400_BAD_REQUEST,
        )

    price_id = getattr(settings, _PRICE_BY_TIER[tier])
    if not price_id:
        return Response(
            {'detail': f'Stripe price for "{tier}" tier is not configured.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    company = _company(request.user)
    if not company:
        return Response({'detail': 'No company on this account.'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Tier is in metadata so the webhook can record which tier the customer
    # ended up on (Stripe doesn't echo the price-id in subscription events
    # in a tier-named way; metadata is the cleanest carry-through).
    try:
        session = stripe.checkout.Session.create(
            mode='subscription',
            customer=company.stripe_customer_id or None,
            line_items=[{'price': price_id, 'quantity': 1}],
            success_url=settings.STRIPE_CHECKOUT_SUCCESS_URL,
            cancel_url=settings.STRIPE_CHECKOUT_CANCEL_URL,
            client_reference_id=str(company.id),
            subscription_data={
                'metadata': {
                    'company_id': str(company.id),
                    'tier': tier,
                },
            },
            metadata={
                'company_id': str(company.id),
                'tier': tier,
            },
        )
    except stripe.error.StripeError as e:
        return Response(
            {'detail': e.user_message or str(e)},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({'url': session.url, 'session_id': session.id})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_portal_session(request):
    """Open Stripe's hosted Customer Portal so the user can update card,
    cancel, or switch plans. Returns {"url": ...}."""
    err = _require_stripe()
    if err:
        return err

    company = _company(request.user)
    if not company or not company.stripe_customer_id:
        return Response(
            {'detail': 'No Stripe customer on this account yet — start a subscription first.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        session = stripe.billing_portal.Session.create(
            customer=company.stripe_customer_id,
            return_url=settings.STRIPE_PORTAL_RETURN_URL,
        )
    except stripe.error.StripeError as e:
        return Response(
            {'detail': e.user_message or str(e)},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({'url': session.url})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_status(request):
    """Lightweight billing snapshot for clients that don't want to pull the
    full /auth/me/ payload."""
    company = _company(request.user)
    if not company:
        return Response({'detail': 'No company on this account.'},
                        status=status.HTTP_400_BAD_REQUEST)
    return Response({
        'tier':                   company.subscription_tier,
        'status':                 company.subscription_status,
        'trial_ends_at':          company.trial_ends_at,
        'current_period_end':     company.current_period_end,
        'has_active_subscription': company.has_active_subscription,
        'has_stripe_customer':    bool(company.stripe_customer_id),
    })
