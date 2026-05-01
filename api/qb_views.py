"""
QuickBooks API endpoints for ContractorHub.

Drop into `api/views_qb.py` (or merge into your existing views.py) and wire
URLs in `api/urls.py` per qb_urls.py in this patch folder.
"""

from django.shortcuts import redirect
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication
from rest_framework.response import Response
import requests
from datetime import datetime, timedelta

from api.models import QBAccount, QBSyncLog, QBGLMapping, Invoice
from api.qb_integration import sync_invoice_to_qb


# ---------- OAuth ----------

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def quickbooks_auth(request):
    """Kick off QB OAuth — returns the redirect URL the client should open."""
    client_id = settings.QB_CLIENT_ID
    redirect_uri = settings.QB_REDIRECT_URI
    auth_url = (
        "https://appcenter.intuit.com/connect/oauth2"
        f"?client_id={client_id}"
        "&response_type=code"
        "&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={redirect_uri}"
        f"&state={request.user.id}"
    )
    return Response({'auth_url': auth_url})


@api_view(['GET'])
@permission_classes([AllowAny])  # callback comes from Intuit, not authenticated by us
def quickbooks_callback(request):
    """Exchange the auth code for an access token and persist the connection."""
    from django.contrib.auth.models import User

    code = request.GET.get('code')
    realm_id = request.GET.get('realmId')
    state = request.GET.get('state')   # contains the user.id we passed in

    if not code or not state:
        return JsonResponse({'error': 'Missing code or state'}, status=400)

    try:
        user = User.objects.get(id=int(state))
    except (User.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Invalid state'}, status=400)

    r = requests.post(
        'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer',
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.QB_REDIRECT_URI,
        },
        auth=(settings.QB_CLIENT_ID, settings.QB_CLIENT_SECRET),
        timeout=15,
    )
    if r.status_code != 200:
        return JsonResponse({'error': 'Token exchange failed', 'detail': r.text}, status=400)

    token_data = r.json()
    QBAccount.objects.update_or_create(
        user=user,
        defaults={
            'access_token': token_data['access_token'],
            'refresh_token': token_data['refresh_token'],
            'token_expires_at': datetime.now() + timedelta(hours=1),
            'realm_id': realm_id,
            'is_connected': True,
        },
    )

    # QB v2: flip the user's Company into "qbo" mode so the QBService factory
    # routes future writes through QBOService. (Prior to this, even after
    # OAuth completed, qb_mode stayed empty and signals never fired.)
    try:
        from api.models import Company
        Company.objects.filter(owner=user).update(qb_mode='qbo')
    except Exception:
        # Don't fail the OAuth completion if this fails — the user can
        # manually flip qb_mode via Django admin.
        pass

    return HttpResponse(
        "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
        "<h2>✅ Connected to QuickBooks</h2>"
        "<p>You can close this window and return to ContractorHub.</p>"
        "</body></html>",
        content_type="text/html",
    )


# ---------- Chart of accounts (Phase 6 — Mac UI default GL pickers) ----------

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def qb_accounts(request):
    """List the QB chart of accounts for the user's company.

    Used by the Mac Settings sheet so the user can pick a default Expense
    account (for vendor Bills) and a default Bank account (for BillPayments).

    Optional query params:
      ?type=expense  → returns only Expense + Cost of Goods Sold accounts
      ?type=bank     → returns only Bank + Credit Card accounts
      (omit)         → returns everything

    Response shape:
      {"results": [{"id": "7", "name": "Advertising", "type": "Expense"}, ...]}
    """
    from api.models import Company
    from api.qb_service import qb_service_for

    company = Company.objects.filter(owner=request.user).first()
    if not company:
        return JsonResponse({"detail": "No company on this account."}, status=400)

    svc = qb_service_for(company)
    try:
        accounts = svc.list_chart_of_accounts()
    except Exception as e:
        return JsonResponse(
            {"detail": f"Could not load chart of accounts: {str(e)[:200]}"},
            status=502,
        )

    type_filter = (request.GET.get("type") or "").lower()
    if type_filter == "expense":
        # Expense + COGS — what you'd post a Bill against.
        keep = {"Expense", "Cost of Goods Sold", "Other Expense"}
        accounts = [a for a in accounts if a.account_type in keep]
    elif type_filter == "bank":
        keep = {"Bank", "Credit Card"}
        accounts = [a for a in accounts if a.account_type in keep]

    return JsonResponse({
        "results": [
            {"id": a.qb_id, "name": a.name, "type": a.account_type}
            for a in accounts if a.is_active
        ]
    })


# ---------- Sync status ----------

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def qb_sync_status(request):
    """Return connection state + recent sync logs (used by the Mac app dashboard)."""
    try:
        qb_account = QBAccount.objects.get(user=request.user)
        is_connected = qb_account.is_connected
        connected_at = qb_account.connected_at
        last_refreshed_at = qb_account.last_refreshed_at
        realm_id = qb_account.realm_id
    except QBAccount.DoesNotExist:
        is_connected = False
        connected_at = None
        last_refreshed_at = None
        realm_id = None

    all_syncs = QBSyncLog.objects.filter(user=request.user)
    recent = all_syncs.order_by('-created_at')[:25]
    total = all_syncs.count()
    successful = all_syncs.filter(status='success').count()
    failed = all_syncs.filter(status='failed').count()
    pending = all_syncs.filter(status='pending').count()
    success_rate = (successful / total * 100) if total else 0

    return Response({
        'is_connected': is_connected,
        'connected_at': connected_at,
        'last_refreshed_at': last_refreshed_at,
        'realm_id': realm_id,
        'success_rate': round(success_rate, 1),
        'total': total,
        'successful': successful,
        'failed': failed,
        'pending': pending,
        'recent_syncs': [
            {
                'id': s.id,
                'object_type': s.object_type,
                'object_id': s.object_id,
                'status': s.status,
                'attempt_count': s.attempt_count,
                'qb_transaction_id': s.qb_transaction_id,
                'error_message': s.error_message,
                'error_code': s.error_code,
                'created_at': s.created_at,
                'synced_at': s.synced_at,
            } for s in recent
        ],
    })


# ---------- Disconnect ----------

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def quickbooks_disconnect(request):
    """Mark the connection as disconnected. Doesn't revoke the token at Intuit."""
    QBAccount.objects.filter(user=request.user).update(is_connected=False)
    return Response({'status': 'disconnected'})


# ---------- Sync invoice on-demand ----------

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def qb_sync_invoice(request):
    """
    Trigger a sync for a specific invoice.
    POST body: {"invoice_id": 123}
    """
    invoice_id = request.data.get('invoice_id')
    if not invoice_id:
        return Response({'error': 'invoice_id required'}, status=400)
    try:
        invoice = Invoice.objects.get(id=invoice_id)
    except Invoice.DoesNotExist:
        return Response({'error': 'Invoice not found'}, status=404)

    result = sync_invoice_to_qb(request.user, invoice)
    status_code = 200 if result.get('status') == 'success' else 400
    return Response(result, status=status_code)


# ---------- GL mapping CRUD ----------

@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def qb_gl_mappings(request):
    if request.method == 'GET':
        mappings = QBGLMapping.objects.filter(user=request.user)
        return Response([
            {
                'id': m.id,
                'category': m.category,
                'gl_account_number': m.gl_account_number,
                'gl_account_name': m.gl_account_name,
            } for m in mappings
        ])

    # POST — create or update by category
    cat = request.data.get('category', '').strip()
    num = request.data.get('gl_account_number', '').strip()
    name = request.data.get('gl_account_name', '').strip()
    if not cat or not num:
        return Response({'error': 'category and gl_account_number required'}, status=400)

    obj, _ = QBGLMapping.objects.update_or_create(
        user=request.user, category=cat,
        defaults={'gl_account_number': num, 'gl_account_name': name},
    )
    return Response({
        'id': obj.id,
        'category': obj.category,
        'gl_account_number': obj.gl_account_number,
        'gl_account_name': obj.gl_account_name,
    })


@api_view(['DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def qb_gl_mapping_detail(request, mapping_id):
    QBGLMapping.objects.filter(user=request.user, id=mapping_id).delete()
    return Response({'status': 'deleted'})
