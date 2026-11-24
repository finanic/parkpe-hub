"""Shared auth contract for both frontends.

Payswap (apps/payswap/js/session.js, origin http://127.0.0.1:4500) sends role
"retailer". ParkPe (apps/parkpe/, origin http://127.0.0.1:4310) is allowlisted
but has no client yet; when it does, it must send role "customer" and must
not import the PaySwap session file. The backend console
(apps/backend/auth/console/console.js, served at http://127.0.0.1:4600/) sends
role "operator". Only the first operator account can be created; later
operator signups are refused.

Cookie paths are host-only on 127.0.0.1, so both apps see the same jar.
The role check on login is what keeps a customer session out of the retailer
counter, and the reverse.
"""

from __future__ import annotations

HEADER = "X-Auth-Request"

ACCESS_COOKIE = "auth_access"
REFRESH_COOKIE = "auth_refresh"
MFA_COOKIE = "auth_mfa"

ACCESS_PATH = "/"
REFRESH_PATH = "/api/auth"
MFA_PATH = "/api/auth/mfa"

SCOPE_ENROLL = "enroll"
SCOPE_FULL = "full"

ROLE_RETAILER = "retailer"
ROLE_CUSTOMER = "customer"
ROLE_OPERATOR = "operator"
ROLES = frozenset({ROLE_RETAILER, ROLE_CUSTOMER, ROLE_OPERATOR})

LOGIN_ERROR = "Email or password is incorrect."


class Paths:
    HEALTH = "/api/health"
    REGISTER = "/api/auth/register"
    LOGIN = "/api/auth/login"
    MFA = "/api/auth/mfa"
    MFA_SETUP = "/api/auth/mfa/setup"
    MFA_CONFIRM = "/api/auth/mfa/confirm"
    REFRESH = "/api/auth/refresh"
    LOGOUT = "/api/auth/logout"
    ME = "/api/auth/me"
    SETUP = "/api/auth/setup"
