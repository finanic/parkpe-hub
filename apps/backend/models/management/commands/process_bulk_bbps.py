"""Claim pending bulk BBPS fetch (and optional pay) rows.

Usage (from repo root, beside make api):
  python3 apps/backend/manage.py process_bulk_bbps
  python3 apps/backend/manage.py process_bulk_bbps --once
  python3 apps/backend/manage.py process_bulk_bbps --limit 10 --sleep 2
"""

from __future__ import annotations

import os
import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Process BulkBbpsRow fetch (and queued pay when PIN is not required) workers."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one claim cycle then exit.")
        parser.add_argument("--limit", type=int, default=0, help="Rows per cycle (default env or 10).")
        parser.add_argument("--sleep", type=float, default=0, help="Seconds between cycles (default env or 2).")
        parser.add_argument("--batch-id", default="", help="Restrict to one batch_id.")

    def handle(self, *args, **options):
        from domain.payswap.bulk_bbps import process_fetch_queue, process_pay_queue

        limit = int(options.get("limit") or 0) or int(os.environ.get("BULK_BBPS_FETCH_LIMIT", "10") or 10)
        sleep_s = float(options.get("sleep") or 0) or float(os.environ.get("BULK_BBPS_SLEEP", "2") or 2)
        batch_id = str(options.get("batch_id") or "").strip()
        once = bool(options.get("once"))
        concurrency = max(1, min(int(os.environ.get("BULK_BBPS_CONCURRENCY", "2") or 2), 3))
        self.stdout.write(
            f"Bulk BBPS worker limit={limit} sleep={sleep_s}s concurrency={concurrency} batch={batch_id or '*'}"
        )
        while True:
            fetched = 0
            for _ in range(concurrency):
                fetched += process_fetch_queue(limit=max(1, limit // concurrency), batch_id=batch_id)
            # Pay queue only advances rows already queued with an in-request PIN (proceed).
            # Worker retries leave pay_error when PIN is absent — admin sync re-fetches only.
            paid = process_pay_queue(limit=max(1, limit // concurrency), batch_id=batch_id, wallet_pin="")
            if fetched or paid:
                self.stdout.write(f"fetched={fetched} pay_touched={paid}")
            if once:
                break
            time.sleep(max(0.5, sleep_s))
