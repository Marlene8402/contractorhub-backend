# ContractorHub API Reference

Base URL: `http://localhost:8000/api/` (local) or `https://<your-app>.railway.app/api/` (production)

All endpoints require: `Authorization: Token <your-token>`

Get a token: `POST /api/auth/token/` with `{"username": "...", "password": "..."}`

All list responses are paginated: `{ "count": N, "next": url|null, "previous": url|null, "results": [...] }`

---

## Authentication

### Get Token
`POST /api/auth/token/`
```json
// Request
{ "username": "admin", "password": "yourpassword" }

// Response
{ "token": "e63ddd263eb9127a788b49e926f71d8a04727efa" }
```

---

## Companies
`GET/POST /api/companies/`
`GET/PUT/PATCH/DELETE /api/companies/{id}/`

```json
{
  "id": 1,
  "name": "Acme Construction",
  "email": "info@acme.com",
  "phone": "555-1234",
  "address": "123 Main St",
  "city": "Austin",
  "state": "TX",
  "zip_code": "78701",
  "qb_connected": false,
  "created_at": "2026-04-28T00:00:00Z"
}
```

Custom actions:
- `GET /api/companies/{id}/qb_auth_url/` — get QuickBooks OAuth URL
- `POST /api/companies/{id}/disconnect_qb/` — disconnect QuickBooks

---

## Projects
`GET /api/projects/` — returns lightweight list (no nested budget/schedule/invoices)
`POST /api/projects/`
`GET/PUT/PATCH/DELETE /api/projects/{id}/` — returns full detail with nested objects

**List item:**
```json
{
  "id": 1,
  "name": "Office Renovation",
  "status": "active",
  "client_name": "Smith Corp",
  "contract_amount": "150000.00",
  "start_date": "2026-05-01",
  "end_date": "2026-08-01",
  "project_manager_name": "Jane Doe"
}
```

**Detail (POST/GET by id):**
```json
{
  "id": 1,
  "name": "Office Renovation",
  "description": "Full office gut and remodel",
  "status": "active",
  "contract_number": "CON-001",
  "client_name": "Smith Corp",
  "contract_amount": "150000.00",
  "bid_due_date": "2026-04-15",
  "start_date": "2026-05-01",
  "end_date": "2026-08-01",
  "project_manager": 1,
  "project_manager_name": "Jane Doe",
  "qb_synced": false,
  "created_at": "2026-04-28T00:00:00Z",
  "updated_at": "2026-04-28T00:00:00Z",
  "budget": { ... },
  "schedule": { ... },
  "invoices": [ ... ]
}
```

Status values: `bidding` `awarded` `active` `on_hold` `completed` `cancelled`

Custom actions:
- `GET /api/projects/active_projects/` — active + awarded projects only
- `GET /api/projects/summary/` — dashboard totals
- `POST /api/projects/{id}/update_schedule/` — update schedule fields
- `POST /api/projects/{id}/update_budget/` — update budget fields

---

## Team Members
`GET/POST /api/team-members/`
`GET/PUT/PATCH/DELETE /api/team-members/{id}/`

```json
{
  "id": 1,
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane@acme.com",
  "phone": "555-5678",
  "role": "Project Manager",
  "is_active": true,
  "created_at": "2026-04-28T00:00:00Z"
}
```

---

## Budgets
`GET/POST /api/budgets/`
`GET/PUT/PATCH/DELETE /api/budgets/{id}/`

```json
{
  "id": 1,
  "project": 1,
  "estimated_labor": "50000.00",
  "estimated_materials": "60000.00",
  "estimated_equipment": "10000.00",
  "estimated_overhead": "15000.00",
  "estimated_profit": "15000.00",
  "actual_labor": "0.00",
  "actual_materials": "0.00",
  "actual_equipment": "0.00",
  "actual_overhead": "0.00",
  "estimated_total": "150000.00",
  "actual_total": "0.00",
  "variance": "150000.00",
  "notes": "",
  "created_at": "2026-04-28T00:00:00Z",
  "updated_at": "2026-04-28T00:00:00Z"
}
```

Custom actions:
- `POST /api/budgets/{id}/sync_to_qb/` — push budget to QuickBooks

---

## Invoices
`GET/POST /api/invoices/`
`GET/PUT/PATCH/DELETE /api/invoices/{id}/`

```json
{
  "id": 1,
  "project": 1,
  "invoice_number": "INV-0001",
  "amount": "25000.00",
  "description": "Phase 1 completion",
  "status": "pending",
  "issue_date": "2026-05-15",
  "due_date": "2026-06-15",
  "paid_date": null,
  "qb_synced": false,
  "created_at": "2026-04-28T00:00:00Z",
  "updated_at": "2026-04-28T00:00:00Z"
}
```

Status values: `draft` `pending` `sent` `paid` `overdue`

Custom actions:
- `POST /api/invoices/{id}/sync_to_qb/` — push invoice to QuickBooks
- `POST /api/invoices/sync_from_qb/` — pull invoices from QuickBooks

---

## Project Schedules
`GET/POST /api/project-schedules/`
`GET/PUT/PATCH/DELETE /api/project-schedules/{id}/`

```json
{
  "id": 1,
  "project": 1,
  "planned_start": "2026-05-01",
  "planned_end": "2026-08-01",
  "actual_start": null,
  "actual_end": null,
  "percent_complete": 0,
  "notes": "",
  "created_at": "2026-04-28T00:00:00Z",
  "updated_at": "2026-04-28T00:00:00Z"
}
```

---

## QB Sync Logs
`GET /api/qb-sync-logs/` — read-only

```json
{
  "id": 1,
  "sync_type": "invoice",
  "status": "success",
  "direction": "push",
  "qb_id": "123",
  "error_message": null,
  "synced_at": "2026-04-28T00:00:00Z"
}
```
