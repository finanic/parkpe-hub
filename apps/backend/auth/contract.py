"""Shared auth contract for both frontends.

Payswap (apps/payswap/js/session.js, origin http://127.0.0.1:4500) sends role
"retailer". ParkPe (apps/parkpe/js/session.js, origin http://127.0.0.1:4310)
sends role "customer" and must not import the PaySwap session file. Customer
and retailer accounts are created by a signed-in admin, on the console
origin, and only after verification. The backend console
(apps/backend/auth/console/console.js, served at http://127.0.0.1:4600/) sends
role "admin". The first admin is created once on /api/auth/register.
Later admins are added from the desk. Public signup is refused.

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
ROLE_ADMIN = "admin"
ROLES = frozenset({ROLE_RETAILER, ROLE_CUSTOMER, ROLE_ADMIN})

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
    DESK = "/api/auth/desk"
    DESK_ACCOUNTS = "/api/auth/desk/accounts"
    DESK_PEOPLE = "/api/auth/desk/people"
    DESK_SIGN_IN = "/api/auth/desk/people/sign-in"
    DESK_SIGNUPS = "/api/auth/desk/signups"
    DESK_PROCESSES = "/api/auth/desk/processes"
    SIGNUP_START = "/api/auth/signup/start"
    SIGNUP_CONTACT = "/api/auth/signup/contact"
    SIGNUP_AADHAAR = "/api/auth/signup/aadhaar"
    SIGNUP_AADHAAR_CONFIRM = "/api/auth/signup/aadhaar/confirm"
    SIGNUP_PAN = "/api/auth/signup/pan"
