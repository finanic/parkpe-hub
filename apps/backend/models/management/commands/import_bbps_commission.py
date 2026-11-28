"""Import Mobikwik B2B commission Excel into VendorCommissionRate.

Usage (from repo root):
  python apps/backend/manage.py import_bbps_commission
  python apps/backend/manage.py import_bbps_commission --file /path/to/sheet.xlsx
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from domain.payswap.commission import default_commission_sheet_path, ensure_commission_catalogue, import_vendor_sheet


class Command(BaseCommand):
    help = "Import Mobikwik B2B commission sheet into VendorCommissionRate (force refresh)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="",
            help="Path to Excel sheet (default: apps/backend/data/mobikwik/commission-b2b.xlsx)",
        )

    def handle(self, *args, **options):
        raw = str(options.get("file") or "").strip()
        path = Path(raw).expanduser() if raw else default_commission_sheet_path()
        if not path.is_file():
            raise CommandError(f"Sheet not found: {path}")
        try:
            # Force=True so ops can re-drop the same mtime file and still refresh.
            result = ensure_commission_catalogue(path=path, force=True, actor="manage.py")
            if not result.get("imported"):
                result = import_vendor_sheet(path, actor="manage.py")
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {result.get('upserted', 0)} rates from {result.get('source', path.name)} "
                f"(skipped {result.get('skipped', 0)})."
            )
        )
