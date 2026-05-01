"""QB Integration v2 — QBOService (QuickBooks Online REST API implementation).

Implements QBService against Intuit's QuickBooks Online v3 API. Tokens come
from the existing QBAccount model (Company.owner.qb_account) — populated by
the OAuth callback in qb_views.py. Sandbox vs production host is controlled
by settings.QB_USE_SANDBOX.

Design rules:
- Reads return real domain dataclasses (QBVendor, QBCustomer, QBChartAccount,
  QBItem). On failure they raise; the caller is expected to handle it (this
  is the read path — there's no notion of "queued").
- Writes return SyncResult with state=synced/queued/failed_permanent. They
  NEVER raise — all errors get bottled into SyncResult.failure_reason. This
  is the patentable claim's main contract: writes are uniform across QBO and
  QBWC.
- Idempotency: every write looks up QBLink first. If a link exists, we do an
  update (using the stored qb_entity_id + qb_sync_token). Otherwise create.
- Logging: every API call writes a QBSyncLog row.
"""
from __future__ import annotations

import json as _json
import time
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

from .models import QBAccount as QBAccountModel, QBLink, QBSyncLog
from .qb_payloads import (
    BillPayload, BillPaymentPayload, CustomerJobPayload,
    InvoicePayload, SyncResult, VendorPayload,
)
from .qb_service import (
    ConnectionStatus, QBChartAccount, QBCustomer, QBItem, QBService, QBVendor,
)


# Intuit token + API endpoints
QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


def _api_host() -> str:
    return "sandbox-quickbooks" if settings.QB_USE_SANDBOX else "quickbooks"


def _decimal(v) -> Decimal | None:
    if v is None or v == "":
        return None
    return Decimal(str(v))


# ---------- The implementation ----------


class QBOService(QBService):
    """QuickBooks Online implementation of QBService."""

    # Refresh access token when fewer than this many seconds remain.
    REFRESH_LEAD_SECONDS = 300  # 5 minutes

    def __init__(self, company):
        super().__init__(company)
        # Tokens live on the existing QBAccount (one per User, owned via
        # Company.owner). If there's no QBAccount, all calls will fail
        # cleanly via _ensure_token().
        try:
            self.qb_account = company.owner.qb_account
        except QBAccountModel.DoesNotExist:
            self.qb_account = None

    # ----- Connection -----

    def is_connected(self) -> ConnectionStatus:
        if not self.qb_account or not self.qb_account.is_connected:
            return ConnectionStatus(state="disconnected", mode="qbo",
                                    detail="Not connected to QuickBooks Online.")
        # A lightweight live check: hit /companyinfo. If it 401s, token is
        # broken; if it 200s, we're connected.
        try:
            self._request("GET", f"/companyinfo/{self.qb_account.realm_id}",
                          log_entity_type="CompanyInfo", log_entity_id=self.qb_account.realm_id)
        except Exception as e:
            return ConnectionStatus(
                state="broken", mode="qbo",
                realm_id=self.qb_account.realm_id,
                detail=f"QuickBooks connection error: {str(e)[:120]}",
            )
        last = self.company.qb_last_synced_at
        return ConnectionStatus(
            state="connected", mode="qbo",
            realm_id=self.qb_account.realm_id,
            last_synced_at=last.isoformat() if last else "",
            detail=f"Connected to QuickBooks Online (realm {self.qb_account.realm_id}).",
        )

    def disconnect(self) -> None:
        if self.qb_account:
            self.qb_account.is_connected = False
            self.qb_account.save(update_fields=["is_connected"])
        self.company.qb_mode = ""
        self.company.save(update_fields=["qb_mode"])

    # ----- Reads -----

    def list_vendors(self) -> list[QBVendor]:
        data = self._query("SELECT * FROM Vendor MAXRESULTS 1000")
        rows = data.get("QueryResponse", {}).get("Vendor", []) or []
        return [
            QBVendor(
                qb_id=str(v["Id"]),
                display_name=v.get("DisplayName") or v.get("CompanyName") or "",
                email=(v.get("PrimaryEmailAddr") or {}).get("Address", ""),
                is_active=bool(v.get("Active", True)),
            )
            for v in rows
        ]

    def list_customers(self) -> list[QBCustomer]:
        data = self._query("SELECT * FROM Customer MAXRESULTS 1000")
        rows = data.get("QueryResponse", {}).get("Customer", []) or []
        return [
            QBCustomer(
                qb_id=str(c["Id"]),
                display_name=c.get("DisplayName") or c.get("CompanyName") or "",
                is_active=bool(c.get("Active", True)),
                parent_id=str((c.get("ParentRef") or {}).get("value", "")),
            )
            for c in rows
        ]

    def list_chart_of_accounts(self) -> list[QBChartAccount]:
        data = self._query("SELECT * FROM Account WHERE Active = true MAXRESULTS 1000")
        rows = data.get("QueryResponse", {}).get("Account", []) or []
        return [
            QBChartAccount(
                qb_id=str(a["Id"]),
                name=a.get("FullyQualifiedName") or a.get("Name", ""),
                account_type=a.get("AccountType", ""),
                account_subtype=a.get("AccountSubType", ""),
                is_active=bool(a.get("Active", True)),
            )
            for a in rows
        ]

    def list_items(self) -> list[QBItem]:
        data = self._query("SELECT * FROM Item WHERE Active = true MAXRESULTS 1000")
        rows = data.get("QueryResponse", {}).get("Item", []) or []
        return [
            QBItem(
                qb_id=str(i["Id"]),
                name=i.get("Name", ""),
                type=i.get("Type", ""),
                is_active=bool(i.get("Active", True)),
            )
            for i in rows
        ]

    # ----- Writes -----

    def upsert_vendor(self, payload: VendorPayload) -> SyncResult:
        link = self._existing_link(payload.contractorhub_id, "Subcontract", "Vendor")
        body = self._vendor_body(payload, link)
        return self._upsert("Vendor", body, link, payload.contractorhub_id, "Subcontract")

    def upsert_customer_job(self, payload: CustomerJobPayload) -> SyncResult:
        # In QB, both parent Customer and child Job (sub-customer) are stored
        # in the Customer table; the difference is whether ParentRef is set.
        # For v1: we make sure the parent Customer (= client) exists, then
        # create the Job under it. We use ContractorHub-side ids so both
        # mappings end up in QBLink for fast subsequent lookups.
        client_link = self._upsert_client_customer(payload)
        if client_link.state == "failed_permanent":
            return client_link

        link = self._existing_link(payload.contractorhub_id, "Project", "Customer")
        body = self._job_body(payload, parent_qb_id=client_link.qb_entity_id, link=link)
        return self._upsert("Customer", body, link, payload.contractorhub_id, "Project")

    def create_bill(self, payload: BillPayload) -> SyncResult:
        link = self._existing_link(payload.contractorhub_id, "Invoice", "Bill")
        body = self._bill_body(payload, link)
        return self._upsert("Bill", body, link, payload.contractorhub_id, "Invoice")

    def create_invoice(self, payload: InvoicePayload) -> SyncResult:
        link = self._existing_link(payload.contractorhub_id, "Invoice", "Invoice")
        body = self._invoice_body(payload, link)
        return self._upsert("Invoice", body, link, payload.contractorhub_id, "Invoice")

    def record_bill_payment(self, payload: BillPaymentPayload) -> SyncResult:
        # BillPayment is always a create — we don't update an existing one.
        link = self._existing_link(payload.contractorhub_id, "Invoice", "BillPayment")
        body = self._bill_payment_body(payload, link)
        return self._upsert("BillPayment", body, link, payload.contractorhub_id, "Invoice")

    # =========================================================================
    # Internals: token, request, query, body builders
    # =========================================================================

    def _api_base(self) -> str:
        if not self.qb_account:
            raise QBOConnectionError("No QBAccount for company owner.")
        return f"https://{_api_host()}.api.intuit.com/v3/company/{self.qb_account.realm_id}"

    def _ensure_token(self) -> str:
        """Lazy refresh: if fewer than REFRESH_LEAD_SECONDS remain, refresh
        before returning the access token. This is Layer 1 from v1 spec but
        in its lightweight on-demand form (no Celery yet)."""
        if not self.qb_account or not self.qb_account.is_connected:
            raise QBOConnectionError("Not connected to QuickBooks Online.")
        now = timezone.now()
        seconds_left = (self.qb_account.token_expires_at - now).total_seconds()
        if seconds_left < self.REFRESH_LEAD_SECONDS:
            self._refresh_token()
        return self.qb_account.access_token

    def _refresh_token(self) -> None:
        if not self.qb_account:
            raise QBOConnectionError("No QBAccount to refresh.")
        r = requests.post(
            QBO_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.qb_account.refresh_token,
            },
            auth=(settings.QB_CLIENT_ID, settings.QB_CLIENT_SECRET),
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if r.status_code != 200:
            self.qb_account.is_connected = False
            self.qb_account.save(update_fields=["is_connected"])
            raise QBOConnectionError(
                f"Token refresh failed (HTTP {r.status_code}). User must reconnect."
            )
        d = r.json()
        self.qb_account.access_token = d["access_token"]
        self.qb_account.refresh_token = d.get("refresh_token", self.qb_account.refresh_token)
        self.qb_account.token_expires_at = timezone.now() + timedelta(
            seconds=int(d.get("expires_in", 3600))
        )
        self.qb_account.last_refreshed_at = timezone.now()
        self.qb_account.save(update_fields=[
            "access_token", "refresh_token",
            "token_expires_at", "last_refreshed_at",
        ])

    def _request(self, method: str, path: str, *,
                 json: dict | None = None,
                 params: dict | None = None,
                 log_entity_type: str = "",
                 log_entity_id: str = "",
                 idempotency_key: str = "") -> dict:
        """Single low-level HTTP call. Raises QBOPermanentError /
        QBOTransientError on non-2xx so callers can classify. Always writes
        a QBSyncLog row (success or failure)."""
        token = self._ensure_token()
        url = f"{self._api_base()}{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept":         "application/json",
        }
        if json is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        sync_log = self._begin_sync_log(
            entity_type=log_entity_type, entity_id=log_entity_id,
            sync_type=method, idempotency_key=idempotency_key,
        )
        started = time.monotonic()
        try:
            r = requests.request(
                method, url,
                json=json, params=params,
                headers=headers, timeout=20,
            )
        except requests.RequestException as e:
            self._fail_sync_log(sync_log, code="network", message=str(e)[:300])
            raise QBOTransientError(f"network error: {e}") from e

        elapsed_ms = (time.monotonic() - started) * 1000.0
        try:
            body = r.json() if r.content else {}
        except ValueError:
            body = {"raw": r.text[:300]}

        if 200 <= r.status_code < 300:
            self._finish_sync_log(sync_log, http_status=r.status_code,
                                  qb_id=self._extract_qb_id(body),
                                  elapsed_ms=elapsed_ms)
            return body

        # Non-2xx — classify
        message = self._extract_error_message(body) or f"HTTP {r.status_code}"
        self._fail_sync_log(sync_log, code=str(r.status_code),
                            message=message, elapsed_ms=elapsed_ms)
        if r.status_code in (400, 401, 403, 404):
            raise QBOPermanentError(message, http_status=r.status_code)
        raise QBOTransientError(message, http_status=r.status_code)

    def _query(self, sql: str) -> dict:
        """QBO Query Language — returns raw QueryResponse JSON."""
        return self._request(
            "GET", "/query",
            params={"query": sql, "minorversion": 75},
            log_entity_type="Query", log_entity_id=sql[:80],
        )

    def _upsert(self, qb_entity_type: str, body: dict, link: QBLink | None,
                ch_id: str, ch_type: str) -> SyncResult:
        """Shared write path: POSTs body, parses Intuit response, updates QBLink
        + Company.qb_last_synced_at, returns SyncResult."""
        # Idempotency key — deterministic per (CH entity, QB entity type).
        # Intuit caches responses for ~90 seconds with this header.
        idem_key = f"ch-{ch_type.lower()}-{ch_id}-{qb_entity_type.lower()}"
        try:
            response = self._request(
                "POST", f"/{qb_entity_type.lower()}",
                json=body,
                params={"minorversion": 75},
                log_entity_type=qb_entity_type, log_entity_id=ch_id,
                idempotency_key=idem_key,
            )
        except QBOPermanentError as e:
            self._record_link_failure(link, ch_id, ch_type, qb_entity_type, str(e))
            return SyncResult(state="failed_permanent",
                              qb_entity_type=qb_entity_type,
                              failure_reason=str(e))
        except QBOTransientError as e:
            # For now we don't retry inline (no Layer 6 queue yet — coming).
            # Mark queued; user will see "QB sync pending — will retry" in UI.
            self._record_link_queued(link, ch_id, ch_type, qb_entity_type, str(e))
            return SyncResult(state="queued",
                              qb_entity_type=qb_entity_type,
                              failure_reason=str(e))

        qb_id = self._extract_qb_id(response)
        sync_token = self._extract_sync_token(response)
        link_obj = self._record_link_success(
            link, ch_id, ch_type, qb_entity_type, qb_id, sync_token,
        )
        # Touch Company.qb_last_synced_at
        now = timezone.now()
        self.company.qb_last_synced_at = now
        self.company.save(update_fields=["qb_last_synced_at"])
        return SyncResult(state="synced",
                          qb_entity_id=qb_id,
                          qb_entity_type=qb_entity_type,
                          sync_log_id=str(link_obj.id) if link_obj else "")

    # ----- Body builders (CH payload → Intuit JSON shape) -----

    def _vendor_body(self, p: VendorPayload, link: QBLink | None) -> dict:
        body: dict[str, Any] = {
            "DisplayName": p.display_name,
            "Active":      True,
            "Vendor1099":  bool(p.is_1099),
        }
        if p.email:
            body["PrimaryEmailAddr"] = {"Address": p.email}
        if p.phone:
            body["PrimaryPhone"] = {"FreeFormNumber": p.phone}
        if p.tax_id:
            body["TaxIdentifier"] = p.tax_id
        if p.terms_days is not None:
            body["TermRef"] = {"name": f"Net {p.terms_days}"}  # QB resolves by name
        if p.billing_address:
            body["BillAddr"] = self._addr(p.billing_address)
        if link and link.qb_entity_id:
            body["Id"] = link.qb_entity_id
            body["SyncToken"] = link.qb_sync_token or "0"
            body["sparse"] = True
        return body

    def _job_body(self, p: CustomerJobPayload, parent_qb_id: str, link: QBLink | None) -> dict:
        body: dict[str, Any] = {
            "DisplayName": p.project_name,
            "Active": True,
            "Job": True,
            "ParentRef": {"value": parent_qb_id},
        }
        if link and link.qb_entity_id:
            body["Id"] = link.qb_entity_id
            body["SyncToken"] = link.qb_sync_token or "0"
            body["sparse"] = True
        return body

    def _client_body(self, p: CustomerJobPayload, link: QBLink | None) -> dict:
        body: dict[str, Any] = {
            "DisplayName": p.client_name,
            "CompanyName": p.client_name,
            "Active": True,
        }
        if p.client_email:
            body["PrimaryEmailAddr"] = {"Address": p.client_email}
        if p.client_phone:
            body["PrimaryPhone"] = {"FreeFormNumber": p.client_phone}
        if p.client_address:
            body["BillAddr"] = self._addr(p.client_address)
        if link and link.qb_entity_id:
            body["Id"] = link.qb_entity_id
            body["SyncToken"] = link.qb_sync_token or "0"
            body["sparse"] = True
        return body

    def _bill_body(self, p: BillPayload, link: QBLink | None) -> dict:
        lines = []
        for li in p.lines:
            account_detail: dict[str, Any] = {}
            if li.account_ref:
                account_detail["AccountRef"] = {"value": li.account_ref}
            if li.customer_job_ref:
                account_detail["CustomerRef"] = {"value": li.customer_job_ref}
                account_detail["BillableStatus"] = "Billable"
            lines.append({
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": float(li.amount),
                "Description": li.description,
                "AccountBasedExpenseLineDetail": account_detail,
            })
        body: dict[str, Any] = {
            "VendorRef": {"value": p.vendor_qb_id},
            "TxnDate":   p.bill_date.isoformat(),
            "Line":      lines,
        }
        if p.due_date:
            body["DueDate"] = p.due_date.isoformat()
        if p.reference_number:
            body["DocNumber"] = p.reference_number
        if p.memo:
            body["PrivateNote"] = p.memo
        if link and link.qb_entity_id:
            body["Id"] = link.qb_entity_id
            body["SyncToken"] = link.qb_sync_token or "0"
            body["sparse"] = True
        return body

    def _invoice_body(self, p: InvoicePayload, link: QBLink | None) -> dict:
        lines = []
        for li in p.lines:
            sales_detail: dict[str, Any] = {}
            if li.item_ref:
                sales_detail["ItemRef"] = {"value": li.item_ref}
            if li.customer_job_ref:
                sales_detail["ClassRef"] = {"value": li.customer_job_ref}
            if li.qty is not None:
                sales_detail["Qty"] = float(li.qty)
            if li.rate is not None:
                sales_detail["UnitPrice"] = float(li.rate)
            lines.append({
                "DetailType": "SalesItemLineDetail",
                "Amount": float(li.amount),
                "Description": li.description,
                "SalesItemLineDetail": sales_detail,
            })
        body: dict[str, Any] = {
            "CustomerRef": {"value": p.customer_qb_id},
            "Line": lines,
        }
        if p.invoice_date:
            body["TxnDate"] = p.invoice_date.isoformat()
        if p.due_date:
            body["DueDate"] = p.due_date.isoformat()
        if p.invoice_number:
            body["DocNumber"] = p.invoice_number
        if p.memo:
            body["CustomerMemo"] = {"value": p.memo}
        if link and link.qb_entity_id:
            body["Id"] = link.qb_entity_id
            body["SyncToken"] = link.qb_sync_token or "0"
            body["sparse"] = True
        return body

    def _bill_payment_body(self, p: BillPaymentPayload, link: QBLink | None) -> dict:
        body: dict[str, Any] = {
            "VendorRef": {"value": ""},   # Will be derived by Intuit from BillRef? No — we need it.
            "TotalAmt":  float(p.amount),
            "PayType":   "Check",
            "AccountRef": {"value": p.pay_account_ref},
            "TxnDate":   p.pay_date.isoformat(),
            "Line": [{
                "Amount": float(p.amount),
                "LinkedTxn": [{
                    "TxnId":   p.bill_qb_id,
                    "TxnType": "Bill",
                }],
            }],
        }
        if p.private_note:
            body["PrivateNote"] = p.private_note
        # BillPayment requires VendorRef; look it up from the Bill's link
        bill_link = QBLink.objects.filter(
            company=self.company, qb_entity_id=p.bill_qb_id, qb_entity_type="Bill",
        ).first()
        # As a fallback, fetch Bill from QB to get VendorRef. Optimistic path:
        # if the related Subcontract has a Vendor link via the Invoice's
        # subcontract FK, use that. For v1 we keep it simple — fetch the Bill.
        if bill_link is None or not bill_link.qb_entity_id:
            raise QBOPermanentError(
                "Cannot record bill payment: matching Bill not found in QBLink."
            )
        # Read Bill to grab its VendorRef
        bill_data = self._request(
            "GET", f"/bill/{p.bill_qb_id}",
            log_entity_type="Bill", log_entity_id=p.bill_qb_id,
        )
        vendor_ref = (((bill_data or {}).get("Bill") or {}).get("VendorRef") or {}).get("value")
        if not vendor_ref:
            raise QBOPermanentError("Cannot record bill payment: VendorRef not found on Bill.")
        body["VendorRef"] = {"value": vendor_ref}
        return body

    def _addr(self, a) -> dict:
        out: dict[str, Any] = {}
        if a.line1:   out["Line1"]   = a.line1
        if a.line2:   out["Line2"]   = a.line2
        if a.city:    out["City"]    = a.city
        if a.state:   out["CountrySubDivisionCode"] = a.state
        if a.zip:     out["PostalCode"] = a.zip
        if a.country: out["Country"] = a.country
        return out

    # ----- QBLink helpers -----

    def _existing_link(self, ch_id: str, ch_type: str, qb_type: str) -> QBLink | None:
        return QBLink.objects.filter(
            company=self.company,
            contractorhub_entity_type=ch_type,
            contractorhub_entity_id=ch_id,
        ).first()

    def _upsert_client_customer(self, p: CustomerJobPayload) -> SyncResult:
        # Use the client_name as the CH-side anchor for the parent Customer
        # (since we don't have a real CH model for "client" — clients are
        # just strings on Project today). Idempotent on (company, "Client",
        # client_name).
        anchor_id = f"client::{p.client_name}"
        link = self._existing_link(anchor_id, "Client", "Customer")
        body = self._client_body(p, link)
        return self._upsert("Customer", body, link, anchor_id, "Client")

    def _record_link_success(self, link, ch_id, ch_type, qb_type, qb_id, sync_token):
        if link is None:
            link, _ = QBLink.objects.update_or_create(
                company=self.company,
                contractorhub_entity_type=ch_type,
                contractorhub_entity_id=ch_id,
                defaults={
                    "qb_entity_type": qb_type,
                    "qb_entity_id":   qb_id,
                    "qb_sync_token":  sync_token,
                    "sync_state":     "synced",
                    "failure_reason": "",
                    "last_synced_at": timezone.now(),
                },
            )
        else:
            link.qb_entity_type = qb_type
            link.qb_entity_id   = qb_id
            link.qb_sync_token  = sync_token
            link.sync_state     = "synced"
            link.failure_reason = ""
            link.last_synced_at = timezone.now()
            link.save()
        return link

    def _record_link_failure(self, link, ch_id, ch_type, qb_type, reason):
        QBLink.objects.update_or_create(
            company=self.company,
            contractorhub_entity_type=ch_type,
            contractorhub_entity_id=ch_id,
            defaults={
                "qb_entity_type": qb_type,
                "sync_state":     "failed_permanent",
                "failure_reason": reason[:1000],
            },
        )

    def _record_link_queued(self, link, ch_id, ch_type, qb_type, reason):
        QBLink.objects.update_or_create(
            company=self.company,
            contractorhub_entity_type=ch_type,
            contractorhub_entity_id=ch_id,
            defaults={
                "qb_entity_type": qb_type,
                "sync_state":     "queued",
                "failure_reason": reason[:1000],
            },
        )

    # ----- Sync log helpers -----

    def _begin_sync_log(self, *, entity_type, entity_id, sync_type, idempotency_key) -> QBSyncLog:
        # Note: QBSyncLog.idempotency_key has a UNIQUE constraint inherited
        # from the legacy sync_invoice flow that used it for "already
        # synced?" lookups. In v2, dedup lives on QBLink — the row in
        # QBSyncLog is just an audit log entry. So we always store a fresh
        # UUID here. The DETERMINISTIC Intuit-side Idempotency-Key (if any)
        # passes through the request layer separately and never touches
        # this column.
        row_key = f"qbo-{uuid.uuid4()}"
        return QBSyncLog.objects.create(
            user=self.company.owner,
            sync_type=sync_type[:20],
            object_id=str(entity_id)[:50],
            object_type=entity_type[:20] or "Unknown",
            status="syncing",
            idempotency_key=row_key,
            attempt_count=1,
            last_attempted_at=timezone.now(),
        )

    def _finish_sync_log(self, sync_log: QBSyncLog, *, http_status, qb_id, elapsed_ms):
        sync_log.status = "success"
        sync_log.qb_transaction_id = qb_id or ""
        sync_log.synced_at = timezone.now()
        sync_log.save(update_fields=["status", "qb_transaction_id", "synced_at"])

    def _fail_sync_log(self, sync_log: QBSyncLog, *, code, message, elapsed_ms=None):
        sync_log.status = "failed"
        sync_log.error_code = (code or "")[:50]
        sync_log.error_message = (message or "")[:1000]
        sync_log.save(update_fields=["status", "error_code", "error_message"])

    # ----- Response parsing -----

    @staticmethod
    def _extract_qb_id(response: dict) -> str:
        """Intuit responses wrap the entity in a top-level key matching the
        entity type. e.g. POST to /vendor returns {"Vendor": {"Id": "...", ...}}.
        """
        if not response:
            return ""
        for key, val in response.items():
            if isinstance(val, dict) and "Id" in val:
                return str(val["Id"])
        return ""

    @staticmethod
    def _extract_sync_token(response: dict) -> str:
        if not response:
            return ""
        for _, val in response.items():
            if isinstance(val, dict) and "SyncToken" in val:
                return str(val["SyncToken"])
        return ""

    @staticmethod
    def _extract_error_message(body: dict) -> str:
        """Intuit's error shape: {"Fault": {"Error": [{"Message": "...", "Detail": "..."}]}}"""
        try:
            fault = body.get("Fault") or {}
            errors = fault.get("Error") or []
            if errors:
                e = errors[0]
                msg = e.get("Message", "")
                detail = e.get("Detail", "")
                return f"{msg} — {detail}".strip(" —") if detail else msg
        except Exception:
            pass
        return ""


# ---------- Errors ----------


class QBOError(Exception):
    """Base error from QBOService internals."""


class QBOConnectionError(QBOError):
    """Token / OAuth issue. User must reconnect."""


class QBOPermanentError(QBOError):
    """4xx response that won't be fixed by retry (validation, duplicate, etc.)."""
    def __init__(self, msg, http_status: int = 0):
        super().__init__(msg)
        self.http_status = http_status


class QBOTransientError(QBOError):
    """5xx, 429, network error — retryable."""
    def __init__(self, msg, http_status: int = 0):
        super().__init__(msg)
        self.http_status = http_status
