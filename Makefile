# ParkPe Hub
#   make parkpe   apps/parkpe/serve.py   http://127.0.0.1:4310
#   make payswap  apps/payswap/serve.py    http://127.0.0.1:4500
#   make hub      apps/backend/run.py      http://127.0.0.1:4600
# Auth allowlists both frontend origins (apps/backend/auth/server.py AUTH_ORIGINS).

PYTHON ?= python3

.PHONY: parkpe payswap hub

parkpe:
	$(PYTHON) apps/parkpe/serve.py

payswap:
	$(PYTHON) apps/payswap/serve.py

hub:
	$(PYTHON) apps/backend/run.py
