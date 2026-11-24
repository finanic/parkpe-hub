"""Route modules for api/v1.

ParkPe handlers (callers: apps/parkpe/features) stay out of PaySwap modules
(callers: apps/payswap/features). Both use deps.py for X-App-Context and
schemas that match packages/contracts.

Mounted by api/v1/urls.py:
  GET  /api/v1/health/
  POST /api/v1/parkpe/sessions/initiate
  POST /api/v1/payswap/vouchers/order

The routes that answer today are Paths in apps/backend/auth/contract.py,
implemented in apps/backend/auth/server.py. apps/payswap/js/session.js calls those.
"""
