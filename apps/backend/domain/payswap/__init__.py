"""PaySwap use cases: cards, vouchers, BBPS, transactions.

Caller: apps/payswap/features, context payswap (api/v1/deps.py).
Does not import domain/parkpe. Money writes take the key from
core/idempotency.py. AEPS and DMT still live only in apps/payswap/js/services.js.

vouchers.py is the routed use case: POST /api/v1/payswap/vouchers/order.
Cards, BBPS, and the transaction list are not routed yet.
"""
