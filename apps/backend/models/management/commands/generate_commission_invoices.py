"""Draft monthly GST commission invoices for GSTIN retailers.

Usage (from repo root):
  python3 apps/backend/manage.py generate_commission_invoices
  python3 apps/backend/manage.py generate_commission_invoices --month 2026-10

Cron (1st of month 02:00):
  0 2 1 * * cd /path/to/Parkpe\\ Hub && python3 apps/backend/manage.py generate_commission_invoices
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from domain.payswap.commission import generate_monthly_invoices


class Command(BaseCommand):
    help = "Auto-draft monthly commission GST invoices for retailers with GSTIN."

    def add_arguments(self, parser):
        parser.add_argument(
            "--month",
            default="",
            help="YYYY-MM (default: previous calendar month)",
        )

    def handle(self, *args, **options):
        month = str(options.get("month") or "").strip()
        try:
            result = generate_monthly_invoices(month=month, actor="manage.py")
        except (ValueError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Month {result['month']}: created {result['created']}, "
                f"reused {result['reused']}, skipped {len(result['skipped'])}."
            )
        )
        for item in result["skipped"][:20]:
            self.stdout.write(f"  skip {item.get('user_id')}: {item.get('reason')}")
