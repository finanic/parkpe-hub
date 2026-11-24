"""ParkPe use cases: parking, FASTag, carpool, QR connect.

Caller: apps/parkpe/features, context parkpe (api/v1/deps.py).
Does not import domain/payswap. Persistence goes through models/.
Outbound issuer calls go through integrations/.

sessions.py is the routed use case: POST /api/v1/parkpe/sessions/initiate.
FASTag and carpool are not routed yet.
"""
