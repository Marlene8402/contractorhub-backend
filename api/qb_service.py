"""QB Integration v2 — the QBService abstraction.

One interface, three implementations:

    QBOService           — REST API to QuickBooks Online (Session B)
    QBWCService          — SOAP polled by Web Connector to QB Desktop (Session C)
    DisconnectedQBService — no-op stub returned when Company is not connected
                            to either. Returns failed_permanent on every write.

The factory `qb_service_for(company)` reads `Company.qb_mode` and dispatches
to the right one. Callers (Django signals, viewsets, ad-hoc scripts) only
ever talk to QBService — they never know which back-end is in use.

This abstraction is the patentable claim. See QB_INTEGRATION_v2_SPEC.md §9.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from .qb_payloads import (
    Address, VendorPayload, CustomerJobPayload,
    BillPayload, InvoicePayload, BillPaymentPayload,
    SyncResult,
)


# ---------- Read-side return shapes ----------


@dataclass(frozen=True)
class ConnectionStatus:
    """What the UI badge shows."""
    state:       Literal["connected", "stale", "broken", "disconnected"]
    mode:        Literal["qbo", "qbwc", ""] = ""
    realm_id:    str = ""               # QBO only
    last_synced_at: str = ""            # ISO8601 string for JSON friendliness
    detail:      str = ""               # human-readable subline ("Connected to Acme Inc · last sync 2 min ago")


@dataclass(frozen=True)
class QBVendor:
    qb_id:        str
    display_name: str
    email:        str = ""
    is_active:    bool = True


@dataclass(frozen=True)
class QBCustomer:
    qb_id:        str
    display_name: str
    is_active:    bool = True
    parent_id:    str = ""              # populated for Jobs (parent = Customer)


@dataclass(frozen=True)
class QBChartAccount:
    """One entry in the QB chart of accounts. Named QBChartAccount (not just
    QBAccount) to disambiguate from the existing Django QBAccount model that
    stores OAuth tokens — they are unrelated concepts."""
    qb_id:           str
    name:            str                # "Cost of Goods Sold:Concrete", etc.
    account_type:    str = ""           # "Expense", "Income", "Bank", "Cost of Goods Sold"
    account_subtype: str = ""
    is_active:       bool = True


@dataclass(frozen=True)
class QBItem:
    qb_id:    str
    name:     str
    type:     str = ""                  # "Service", "Inventory", etc.
    is_active: bool = True


# ---------- The abstraction ----------


class QBService(ABC):
    """One interface that QBOService, QBWCService, and DisconnectedQBService
    all satisfy. Callers depend on this; the rest of the app never knows
    which back-end is in use for a given Company."""

    def __init__(self, company):
        self.company = company

    # ----- Connection -----

    @abstractmethod
    def is_connected(self) -> ConnectionStatus: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    # ----- Reads (pull from QB) -----

    @abstractmethod
    def list_vendors(self) -> list[QBVendor]: ...

    @abstractmethod
    def list_customers(self) -> list[QBCustomer]: ...

    @abstractmethod
    def list_chart_of_accounts(self) -> list[QBChartAccount]: ...

    @abstractmethod
    def list_items(self) -> list[QBItem]: ...

    # ----- Writes (push to QB) -----

    @abstractmethod
    def upsert_vendor(self, payload: VendorPayload) -> SyncResult: ...

    @abstractmethod
    def upsert_customer_job(self, payload: CustomerJobPayload) -> SyncResult: ...

    @abstractmethod
    def create_bill(self, payload: BillPayload) -> SyncResult: ...

    @abstractmethod
    def create_invoice(self, payload: InvoicePayload) -> SyncResult: ...

    @abstractmethod
    def record_bill_payment(self, payload: BillPaymentPayload) -> SyncResult: ...


# ---------- DisconnectedQBService — the safe no-op ----------


class DisconnectedQBService(QBService):
    """Returned when Company.qb_mode is empty. Every write fails permanently
    with a clear "not connected" reason. Reads return empty lists.

    Why a real implementation rather than `None`: the rest of the app never
    has to null-check. Calling `qb.create_bill(...)` is always safe; it just
    returns a SyncResult the caller can react to."""

    def is_connected(self) -> ConnectionStatus:
        return ConnectionStatus(
            state="disconnected",
            mode="",
            detail="Not connected to QuickBooks. Connect in Settings → QuickBooks.",
        )

    def disconnect(self) -> None:
        return  # already disconnected

    def list_vendors(self) -> list[QBVendor]:                  return []
    def list_customers(self) -> list[QBCustomer]:              return []
    def list_chart_of_accounts(self) -> list[QBChartAccount]:  return []
    def list_items(self) -> list[QBItem]:                       return []

    def _fail(self) -> SyncResult:
        return SyncResult(
            state="failed_permanent",
            failure_reason="Not connected to QuickBooks. Connect in Settings → QuickBooks.",
        )

    def upsert_vendor(self, payload):       return self._fail()
    def upsert_customer_job(self, payload): return self._fail()
    def create_bill(self, payload):         return self._fail()
    def create_invoice(self, payload):      return self._fail()
    def record_bill_payment(self, payload): return self._fail()


# ---------- Factory ----------


def qb_service_for(company) -> QBService:
    """Return the right QBService implementation for this Company.

    Reads Company.qb_mode:
      ""    → DisconnectedQBService (no-op, safe to call)
      "qbo" → QBOService (Session B target)
      "qbwc"→ QBWCService (Session C target)
    """
    mode = (company.qb_mode or "").lower()
    if mode == "qbo":
        # Session B: import lazily so this module stays importable even
        # before QBOService exists.
        from .qb_qbo import QBOService
        return QBOService(company)
    elif mode == "qbwc":
        from .qb_qbwc import QBWCService  # Session C — will exist in C
        return QBWCService(company)
    else:
        return DisconnectedQBService(company)
