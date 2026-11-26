"""Outbound adapters (FASTag issuers, BBPS billers, and later card or voucher hosts).

Called from domain/parkpe or domain/payswap, not from apps/parkpe or
apps/payswap. Secrets for those hosts stay in the environment, same rule
as AUTH_* in apps/backend/auth/server.py. No keys in this package.

parking.py is called by domain/parkpe/parking.py.
bbps.py is called by domain/payswap/bbps.py.
Neither function leaves the machine yet.
kaleyra.py is called by auth/verify.py LiveVerify.send_sms.
"""
