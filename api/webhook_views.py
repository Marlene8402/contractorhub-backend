"""Stripe webhook receiver. NOT authenticated by token — Stripe authenticates
via the signature header verified against STRIPE_WEBHOOK_SECRET."""
from datetime import datetime, timezone as dt_tz

import stripe
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Company


# Stripe events we act on. Anything else returns 200 (ignored, not an error).
_HANDLED_EVENTS = {
    'checkout.session.completed',
    'customer.subscription.created',
    'customer.subscription.updated',
    'customer.subscription.deleted',
    'invoice.payment_failed',
}


def _ts_to_dt(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=dt_tz.utc)


def _company_for(stripe_obj):
    """Resolve the Company associated with a Stripe object — try the customer
    id first, then metadata.company_id as fallback."""
    customer_id = stripe_obj.get('customer')
    if customer_id:
        company = Company.objects.filter(stripe_customer_id=customer_id).first()
        if company:
            return company
    metadata = stripe_obj.get('metadata') or {}
    company_id = metadata.get('company_id')
    if company_id:
        return Company.objects.filter(id=company_id).first()
    return None


def _apply_subscription(company, sub):
    """Mirror a Stripe subscription object onto the Company row."""
    company.stripe_subscription_id = sub['id']
    # Stripe statuses: trialing, active, past_due, canceled, unpaid, incomplete,
    # incomplete_expired. We collapse to our 5 states.
    s = sub.get('status', '')
    status_map = {
        'trialing':           Company.STATUS_TRIALING,
        'active':             Company.STATUS_ACTIVE,
        'past_due':           Company.STATUS_PAST_DUE,
        'unpaid':             Company.STATUS_PAST_DUE,
        'canceled':           Company.STATUS_CANCELED,
        'incomplete':         Company.STATUS_PAST_DUE,
        'incomplete_expired': Company.STATUS_CANCELED,
    }
    company.subscription_status = status_map.get(s, Company.STATUS_NONE)

    metadata = sub.get('metadata') or {}
    tier = metadata.get('tier')
    if tier in {Company.TIER_STARTER, Company.TIER_PRO, Company.TIER_SCALE}:
        company.subscription_tier = tier

    # Stripe's API rev moved current_period_end onto the subscription item;
    # fall back to the legacy top-level field if needed.
    cpe = sub.get('current_period_end')
    if cpe is None:
        items = (sub.get('items') or {}).get('data') or []
        if items:
            cpe = items[0].get('current_period_end')
    company.current_period_end = _ts_to_dt(cpe)

    company.save(update_fields=[
        'stripe_subscription_id', 'subscription_status',
        'subscription_tier', 'current_period_end', 'updated_at',
    ])


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Verify signature, dispatch the event. Always returns 200 unless the
    signature is invalid or we genuinely failed to process — Stripe retries
    on non-2xx for ~3 days, so 5xx must be reserved for actual failures."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        # Misconfigured server. 503 means Stripe will retry.
        return HttpResponse('Webhook secret not configured.', status=503)

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse('Invalid signature', status=400)

    event_type = event['type']
    if event_type not in _HANDLED_EVENTS:
        return HttpResponse(status=200)  # ack; nothing to do

    obj = event['data']['object']

    if event_type == 'checkout.session.completed':
        # Pull the subscription this checkout produced and mirror it.
        company = _company_for(obj)
        sub_id = obj.get('subscription')
        if company and sub_id:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            sub = stripe.Subscription.retrieve(sub_id)
            # Carry tier from session metadata if subscription doesn't have it.
            if not (sub.get('metadata') or {}).get('tier'):
                sub.metadata['tier'] = (obj.get('metadata') or {}).get('tier', '')
            _apply_subscription(company, sub)
            # Trial fields are managed by Stripe from this point on.
            company.trial_ends_at = _ts_to_dt(sub.get('trial_end'))
            company.save(update_fields=['trial_ends_at', 'updated_at'])

    elif event_type in ('customer.subscription.created',
                        'customer.subscription.updated',
                        'customer.subscription.deleted'):
        company = _company_for(obj)
        if company:
            _apply_subscription(company, obj)

    elif event_type == 'invoice.payment_failed':
        company = _company_for(obj)
        if company:
            company.subscription_status = Company.STATUS_PAST_DUE
            company.save(update_fields=['subscription_status', 'updated_at'])

    return HttpResponse(status=200)
