"""Rules both products share (ids, money amounts, state names).

No parking copy and no retailer-counter copy. Product rules go in
domain/parkpe (callers: apps/parkpe) or domain/payswap (callers: apps/payswap).
Shared wire shapes belong in packages/contracts, mirrored by schemas/.

scope.py is the parkpe/customer and payswap/retailer map. api/v1/deps.py
and core/security.py both use it. operator is not a context.
audit.py is the shared line both domain/parkpe/sessions.py and
domain/payswap/vouchers.py attach to a successful response.
"""
