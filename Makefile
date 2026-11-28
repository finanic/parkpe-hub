# ParkPe Hub — from repo root:
#   make parkpe   → http://127.0.0.1:4310
#   make payswap  → http://127.0.0.1:4500
#   make hub      → http://127.0.0.1:4600  (auth + admin console)
#   make api      → http://127.0.0.1:4610  (Django /api/v1)
#   make dev      → all four (Ctrl+C stops all)
#
# Commission (auto on API boot from apps/backend/data/mobikwik/commission-b2b.xlsx):
#   python3 apps/backend/manage.py import_bbps_commission
#   python3 apps/backend/manage.py generate_commission_invoices
# Cron (1st of month 02:00): 0 2 1 * * cd REPO && python3 apps/backend/manage.py generate_commission_invoices

PYTHON ?= python3

.DEFAULT_GOAL := help

.PHONY: help parkpe payswap hub api bulk-bbps dev

help:
	@echo "ParkPe Hub"
	@echo "  make parkpe   ParkPe app        http://127.0.0.1:4310"
	@echo "  make payswap  PaySwap counter   http://127.0.0.1:4500"
	@echo "  make hub      Auth + console    http://127.0.0.1:4600"
	@echo "  make api      Django /api/v1    http://127.0.0.1:4610"
	@echo "  make bulk-bbps  Bulk BBPS fetch worker (beside make api)"
	@echo "  make dev      Start all four    (see dev.py)"
	@echo "  Commission rates auto-load on API start; monthly GST invoices:"
	@echo "    python3 apps/backend/manage.py generate_commission_invoices"

parkpe:
	$(PYTHON) apps/parkpe/serve.py

payswap:
	$(PYTHON) apps/payswap/serve.py

hub:
	$(PYTHON) apps/backend/run.py

api:
	$(PYTHON) apps/backend/manage.py runserver --noreload 127.0.0.1:4610

bulk-bbps:
	$(PYTHON) apps/backend/manage.py process_bulk_bbps

dev:
	$(PYTHON) dev.py