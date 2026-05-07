"""Signup + identity endpoints.

The existing token-issue endpoint at /api/auth/token/ (DRF's
`obtain_auth_token`) handles login. This module adds:

  POST /api/auth/register/   create User + Company + TeamMember + Stripe
                              customer + 14-day trial; returns token
  GET  /api/auth/me/          identity / company / billing snapshot
"""
from datetime import timedelta

import stripe
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import (
    api_view, permission_classes, throttle_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .audit import log_audit
from .models import Company, TeamMember
from .serializers import CompanySerializer
from .throttles import LoginAnonThrottle, RegisterAnonThrottle


class RegisterSerializer(serializers.Serializer):
    """Signup payload. Email is the username (we don't expose Django's
    separate username field — one less thing for the user to think about)."""
    email        = serializers.EmailField()
    password     = serializers.CharField(write_only=True, min_length=8)
    company_name = serializers.CharField(max_length=255)
    first_name   = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name    = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone        = serializers.CharField(max_length=20,  required=False, allow_blank=True)

    def validate_email(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value.lower()

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value


def _create_stripe_customer(company, user):
    """Create a Stripe customer for this company. Returns the customer id, or
    empty string if Stripe isn't configured (so local dev still works)."""
    if not settings.STRIPE_SECRET_KEY:
        return ''
    stripe.api_key = settings.STRIPE_SECRET_KEY
    customer = stripe.Customer.create(
        email=company.email,
        name=company.name,
        metadata={
            'company_id': str(company.id),
            'user_id':    str(user.id),
        },
    )
    return customer.id


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([RegisterAnonThrottle])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    trial_ends_at = timezone.now() + timedelta(days=settings.SIGNUP_TRIAL_DAYS)

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=data['email'],
                email=data['email'],
                password=data['password'],
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
            )
            company = Company.objects.create(
                owner=user,
                name=data['company_name'],
                email=data['email'],
                phone=data.get('phone', ''),
                subscription_status=Company.STATUS_TRIALING,
                trial_ends_at=trial_ends_at,
            )
            TeamMember.objects.create(
                company=company,
                user=user,
                first_name=data.get('first_name') or data['email'].split('@')[0],
                last_name=data.get('last_name', ''),
                email=data['email'],
                phone=data.get('phone', ''),
                role='admin',
            )
            # Stripe customer creation runs inside the txn so a Stripe outage
            # doesn't leave us with an orphaned User/Company. The save is on
            # the Company row, which is already in the txn.
            company.stripe_customer_id = _create_stripe_customer(company, user)
            company.save(update_fields=['stripe_customer_id'])
            token, _ = Token.objects.get_or_create(user=user)
    except IntegrityError as exc:
        # We only want to reframe the *username uniqueness* race here:
        # serializer.validate_email already rejects duplicates, but two
        # signups for the same email between that check and create_user
        # can both reach this point. Any OTHER IntegrityError (NOT NULL
        # without default, FK violation, etc.) is a real bug — let it
        # bubble to the default 500 handler so we see it in logs and
        # don't mislead users with a "duplicate email" message that
        # masks the real issue (this exact misdiagnosis happened on
        # 2026-05-01 when QB v2 NOT NULL columns lacked defaults and
        # every signup got reframed as "already exists").
        msg = str(exc).lower()
        if 'auth_user_username' in msg or 'username' in msg:
            return Response(
                {'email': ['An account with this email already exists.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        raise
    except stripe.error.StripeError as e:
        return Response(
            {'detail': f'Billing setup failed: {e.user_message or str(e)}'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    log_audit(
        action='signup',
        request=request,
        user=user,
        company=company,
        metadata={'email': data['email']},
    )

    return Response(
        {
            'token': token.key,
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            },
            'company': CompanySerializer(company).data,
        },
        status=status.HTTP_201_CREATED,
    )

class ThrottledObtainAuthToken(ObtainAuthToken):
    """Login endpoint with anonymous per-IP rate limiting. Mounted at
    /api/auth/token/ in api/urls.py in place of the unthrottled
    obtain_auth_token. Defends against credential-stuffing botnets.
    Also writes an AuditLog row on every login attempt (success or
    failure) so abnormal access patterns are visible after the fact."""
    throttle_classes = [LoginAnonThrottle]

    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
        except Exception:
            # On failure, try to resolve the username to a real user so
            # the audit row ties to that user's company. Account-takeover
            # attempts then surface in the victim's audit log.
            attempted_username = request.data.get('username', '')
            target_user = None
            target_company = None
            if attempted_username:
                target_user = User.objects.filter(
                    username__iexact=attempted_username
                ).first()
                if target_user:
                    target_company = Company.objects.filter(
                        owner=target_user
                    ).first()
            log_audit(
                action='login_failed',
                request=request,
                user=target_user,
                company=target_company,
                metadata={'username': attempted_username[:200]},
            )
            raise
        # Successful — pull the user back out of the validated serializer.
        serializer = self.serializer_class(data=request.data,
                                            context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data.get('user')
            log_audit(action='login', request=request, user=user)
        return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    """Identity + company + billing snapshot for the authenticated user.
    Mac app + web app both call this on launch to hydrate session state."""
    company = Company.objects.filter(owner=request.user).first()
    return Response({
        'user': {
            'id': request.user.id,
            'email': request.user.email,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        },
        'company': CompanySerializer(company).data if company else None,
    })
