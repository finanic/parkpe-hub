"""Shared auth contract for both frontends.

Payswap (apps/payswap/js/session.js, origin http://127.0.0.1:4500) sends role
"retailer". ParkPe (apps/parkpe/js/session.js, origin http://127.0.0.1:4310)
sends role "customer" and must not import the PaySwap session file. Customer
and retailer accounts are created by a signed-in admin, on the console
origin, and only after verification. The same email and mobile may be used for
both products, but each role is its own user row, password, and session. The
backend console
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
    PROFILE = "/api/auth/profile"
    PASSWORD_CHANGE = "/api/auth/password/change"
    SELF_SESSIONS = "/api/auth/sessions"
    SELF_SESSIONS_REVOKE = "/api/auth/sessions/revoke"
    SETUP = "/api/auth/setup"
    DESK = "/api/auth/desk"
    DESK_OVERVIEW = "/api/auth/desk/overview"
    DESK_ACCOUNTS = "/api/auth/desk/accounts"
    DESK_PEOPLE = "/api/auth/desk/people"
    DESK_USER_FILE = "/api/auth/desk/users/file"
    DESK_VERIFICATION_RECORD = "/api/auth/desk/users/verification-record"
    DESK_SIGN_IN = "/api/auth/desk/people/sign-in"
    DESK_SIGNUPS = "/api/auth/desk/signups"
    DESK_PROCESSES = "/api/auth/desk/processes"
    DESK_SERVICES = "/api/auth/desk/services"
    DESK_ROLE = "/api/auth/desk/people/role"
    DESK_PASSWORD = "/api/auth/desk/people/password"
    DESK_AUTHENTICATOR = "/api/auth/desk/people/authenticator"
    DESK_SESSIONS = "/api/auth/desk/people/sessions"
    DESK_PARKPE = "/api/auth/desk/parkpe"
    DESK_PAYSWAP = "/api/auth/desk/payswap"
    DESK_ENTITLEMENTS_DEFAULT = "/api/auth/desk/entitlements/default"
    DESK_ENTITLEMENTS_DEFAULT_BBPS_BILLERS = "/api/auth/desk/entitlements/default/bbps-billers"
    DESK_ENTITLEMENTS_RETAILER = "/api/auth/desk/entitlements/retailer"
    DESK_WALLETS = "/api/auth/desk/wallets"
    DESK_WALLETS_TOPUP_REVIEW = "/api/auth/desk/wallets/topup-review"
    DESK_WALLETS_ADJUST = "/api/auth/desk/wallets/adjust"
    DESK_WALLETS_ADJUST_REVIEW = "/api/auth/desk/wallets/adjust-review"
    DESK_WALLETS_CONTROLS = "/api/auth/desk/wallets/controls"
    DESK_TRANSACTIONS = "/api/auth/desk/transactions"
    DESK_TRANSACTIONS_BBPS_SYNC = "/api/auth/desk/transactions/bbps-sync"
    DESK_TRANSACTIONS_PG_SYNC = "/api/auth/desk/transactions/pg-sync"
    DESK_BBPS_BULK = "/api/auth/desk/bbps/bulk"
    DESK_BBPS_BULK_BATCH = "/api/auth/desk/bbps/bulk/batch"
    DESK_COMMISSION_POLICY = "/api/auth/desk/commission/policy"
    DESK_COMMISSION_RATES = "/api/auth/desk/commission/rates"
    DESK_COMMISSION_RATES_IMPORT = "/api/auth/desk/commission/rates/import"
    DESK_COMMISSION_RETAILER = "/api/auth/desk/commission/retailer"
    DESK_COMMISSION_REVENUE = "/api/auth/desk/commission/revenue"
    DESK_COMMISSION_TDS = "/api/auth/desk/commission/tds"
    DESK_COMMISSION_TDS_CERTIFICATE = "/api/auth/desk/commission/tds/certificate"
    DESK_COMMISSION_INVOICES = "/api/auth/desk/commission/invoices"
    DESK_LOGS = "/api/auth/desk/logs"
    DESK_PARKPE_CLOSE = "/api/auth/desk/parkpe/close"
    SIGNUP_START = "/api/auth/signup/start"
    SIGNUP_CANCEL = "/api/auth/signup/cancel"
    SIGNUP_RESEND = "/api/auth/signup/resend"
    SIGNUP_CONTACT = "/api/auth/signup/contact"
    SIGNUP_AADHAAR = "/api/auth/signup/aadhaar"
    SIGNUP_AADHAAR_STATUS = "/api/auth/signup/aadhaar/status"
    SIGNUP_AADHAAR_CONFIRM = "/api/auth/signup/aadhaar/confirm"
    SIGNUP_PAN = "/api/auth/signup/pan"
    SIGNUP_BUSINESS = "/api/auth/signup/business"
    DESK_BUSINESS_REVIEW = "/api/auth/desk/business-review"
