"""A1.6 endpoints: ProjectPhase, ScheduleItem (5 kinds), ProjectTask + child
entities (subtasks/comments/handoffs/watchers), TaskTemplate, BudgetLineItem,
BudgetAllocation. Mirrors /tmp/a1_6_smoke.py."""
from datetime import date
from .base import BaseAPITestCase


class ProjectPhaseTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_create_two_phases_unique_per_project(self):
        for name, order in [("Mobilization", 1), ("Foundation", 2)]:
            r = self.client.post("/api/project-phases/", {
                "project": self.proj1.id, "name": name, "sort_order": order,
            }, format="json")
            self.assertEqual(r.status_code, 201, r.content)
        # Duplicate name on same project should 400 (unique_together)
        r = self.client.post("/api/project-phases/", {
            "project": self.proj1.id, "name": "Mobilization", "sort_order": 3,
        }, format="json")
        self.assertEqual(r.status_code, 400)


class ScheduleItemTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_create_each_kind(self):
        # Milestone
        r = self.client.post("/api/schedule-items/", {
            "project": self.proj1.id, "kind": "milestone",
            "title": "Permits in hand",
            "start_date": "2026-05-15", "end_date": "2026-05-15",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)

        # Submittal with spec section
        r = self.client.post("/api/schedule-items/", {
            "project": self.proj1.id, "kind": "submittal",
            "title": "Insulation submittal",
            "spec_section": "07 21 13",
            "submitted_date": "2026-05-01",
            "required_by_date": "2026-05-10",
            "approval_status": "submitted",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)

        # RFI
        r = self.client.post("/api/schedule-items/", {
            "project": self.proj1.id, "kind": "rfi",
            "title": "Slab rebar spacing",
            "rfi_number": "RFI-001",
            "question": "Is #5 @ 12 OC ok?",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_filter_by_kind(self):
        # Seed one of each kind, then filter
        for k in ["task", "milestone", "submittal", "rfi", "look_ahead"]:
            self.client.post("/api/schedule-items/", {
                "project": self.proj1.id, "kind": k, "title": f"x-{k}",
            }, format="json")
        r = self.client.get(f"/api/schedule-items/?project={self.proj1.id}&kind=submittal")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 1)


class ProjectTaskTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def _make_task(self):
        r = self.client.post("/api/project-tasks/", {
            "project": self.proj1.id, "title": "Pour footings",
            "category": "subcontractor", "priority": "high",
            "photo_filenames": ["IMG.jpg"],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def test_create_returns_empty_embedded_collections(self):
        body = self.client.get(f"/api/project-tasks/{self._make_task()}/").json()
        self.assertEqual(body["subtasks"],    [])
        self.assertEqual(body["comments"],    [])
        self.assertEqual(body["handoffs"],    [])
        self.assertEqual(body["watcher_ids"], [])

    def test_subtask_comment_handoff_watcher_embed_after_create(self):
        tid = self._make_task()

        self.client.post("/api/subtasks/", {
            "task": tid, "title": "Lay rebar", "sort_order": 1,
        }, format="json")
        self.client.post("/api/task-comments/", {
            "task": tid, "author_name": "Test", "text": "Schedule for Tue.",
        }, format="json")
        self.client.post("/api/task-handoffs/", {
            "task": tid, "from_name": "A", "to_name": "B", "note": "yours",
        }, format="json")
        r = self.client.post("/api/task-watchers/", {
            "task": tid, "team_member": self.tm1.id,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)

        body = self.client.get(f"/api/project-tasks/{tid}/").json()
        self.assertEqual(len(body["subtasks"]),    1)
        self.assertEqual(len(body["comments"]),    1)
        self.assertEqual(len(body["handoffs"]),    1)
        self.assertEqual(body["watcher_ids"],      [self.tm1.id])


class TaskTemplateTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_create_with_subtask_titles_json(self):
        r = self.client.post("/api/task-templates/", {
            "name": "Punch closeout", "title": "Final walk",
            "category": "punch", "priority": "normal",
            "subtask_titles": ["paint touchup", "caulk", "door alignment"],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["subtask_titles"],
                         ["paint touchup", "caulk", "door alignment"])

    def test_company_scoped_not_project_scoped(self):
        # Templates aren't filtered by project — they're shared across the company.
        self.client.post("/api/task-templates/", {
            "name": "X", "title": "X",
        }, format="json")
        r = self.client.get("/api/task-templates/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 1)


class BudgetLineItemAndAllocationTests(BaseAPITestCase):
    def setUp(self): self.auth1()

    def test_line_item_then_allocation_against_invoice(self):
        r = self.client.post("/api/budget-line-items/", {
            "project": self.proj1.id, "csi_code": "03 30 00",
            "csi_title": "Cast-in-Place Concrete",
            "description": "Footings + walls",
            "budgeted_amount": "45000.00", "sort_order": 1,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        line_id = r.json()["id"]

        r = self.client.post("/api/budget-allocations/", {
            "invoice": self.inv1.id, "line_item": line_id,
            "csi_code": "03 30 00", "amount": "5000.00",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(float(r.json()["amount"]), 5_000.0)


class A1_6TenantIsolationTests(BaseAPITestCase):
    """Co2 must see zero of Co1's A1.6 entities across the board."""

    def setUp(self):
        # Seed one of each entity under co1
        self.auth1()
        self.client.post("/api/project-tasks/", {
            "project": self.proj1.id, "title": "co1-task",
        }, format="json")
        self.client.post("/api/schedule-items/", {
            "project": self.proj1.id, "kind": "milestone", "title": "co1-mile",
        }, format="json")
        self.client.post("/api/budget-line-items/", {
            "project": self.proj1.id, "csi_code": "03 30 00",
            "budgeted_amount": "1.00",
        }, format="json")
        self.client.post("/api/task-templates/", {
            "name": "co1-tmpl", "title": "co1",
        }, format="json")
        self.client.post("/api/project-phases/", {
            "project": self.proj1.id, "name": "co1-phase",
        }, format="json")
        # Switch to co2 for assertions
        self.auth2()

    def test_zero_visible_to_other_tenant(self):
        for path in ("/api/project-tasks/", "/api/schedule-items/",
                     "/api/budget-line-items/", "/api/task-templates/",
                     "/api/project-phases/"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, f"{path} → {r.status_code}")
            self.assertEqual(r.json()["count"], 0,
                             f"{path} leaked {r.json()['count']} rows")
