"""Data migration: backfill Vendor rows from existing Subcontract.vendor_name
strings, then point Subcontract.vendor at the matching Vendor.

The schema migration (0010) added `Vendor` + `Subcontract.vendor` (nullable).
Here we walk every Subcontract, group by (company, vendor_name), and create
one Vendor per group. We also lift the Subcontract's 1099 fields onto the
Vendor as the new source of truth.

Idempotent: re-running is a no-op (uses get_or_create on (company, name)).
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Subcontract = apps.get_model("api", "Subcontract")
    Vendor      = apps.get_model("api", "Vendor")

    for sub in Subcontract.objects.all():
        if sub.vendor_id is not None:
            continue  # already linked
        company = sub.project.company
        name = (sub.vendor_name or "").strip()
        if not name:
            # Nothing to migrate — Subcontract has no vendor name. Leave
            # vendor=null; user can fix on next edit.
            continue
        vendor, _ = Vendor.objects.get_or_create(
            company=company,
            name=name,
            defaults={
                "email":          sub.vendor_email or "",
                "phone":          sub.vendor_phone or "",
                "is_1099_vendor": getattr(sub, "is_1099_vendor", False) or False,
                "vendor_tax_id":  getattr(sub, "vendor_tax_id", "") or "",
            },
        )
        sub.vendor = vendor
        sub.save(update_fields=["vendor"])


def reverse(apps, schema_editor):
    # Best-effort reverse: drop every Vendor we'd created (we can't tell which
    # were created by this migration vs manually, so we wipe the FK on
    # Subcontracts but leave Vendor rows in place).
    Subcontract = apps.get_model("api", "Subcontract")
    Subcontract.objects.update(vendor=None)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0010_vendor_master"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
