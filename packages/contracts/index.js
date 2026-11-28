/* Shared DTOs, enums, and error codes.

   Consumers: apps/parkpe, apps/payswap, packages/sdk-client,
   and apps/backend/schemas (same field names).
   Live auth names stay in apps/backend/auth/contract.py
   (Paths, cookies, ROLE_CUSTOMER, ROLE_RETAILER, ROLE_ADMIN, X-Auth-Request).
   Role below is the shared spelling of those three role strings.
   apps/parkpe/js/session.js and apps/payswap/js/session.js import it.
   Auth paths are not listed here, so this file cannot drift from Paths.
*/

export const AppContext = Object.freeze({
  PARKPE: "parkpe",
  PAYSWAP: "payswap",
});

export const Role = Object.freeze({
  CUSTOMER: "customer",
  RETAILER: "retailer",
  ADMIN: "admin",
});

export const ErrorCode = Object.freeze({
  UNAUTHENTICATED: "unauthenticated",
  FORBIDDEN_APP: "forbidden_app",
  SERVICE_DISABLED: "service_disabled",
  PAYMENT_MODE_DISABLED: "payment_mode_disabled",
  INSUFFICIENT_BALANCE: "insufficient_balance",
  WALLET_FROZEN: "wallet_frozen",
  LIMIT_EXCEEDED: "limit_exceeded",
  PIN_REQUIRED: "pin_required",
  PIN_LOCKED: "pin_locked",
  VALIDATION: "validation",
  IDEMPOTENCY_CONFLICT: "idempotency_conflict",
  SERVER_ERROR: "server_error",
  BULK_FETCH_FAILED: "bulk_fetch_failed",
  BULK_PAY_FAILED: "bulk_pay_failed",
  BULK_INSUFFICIENT_FLOAT: "bulk_insufficient_float",
  BULK_PIPE_UNAVAILABLE: "bulk_pipe_unavailable",
});

export const RetailerService = Object.freeze({
  BBPS: "bbps",
  WALLET: "wallet",
  TRANSACTIONS: "transactions",
  PROFILE: "profile",
  SUPPORT: "support",
  RECHARGE: "recharge",
  VOUCHERS: "vouchers",
  DMT: "dmt",
  AEPS: "aeps",
});

export const PaymentRail = Object.freeze({
  WALLET: "wallet",
  PG: "pg",
});

/* Economics monetization modes for ServiceEconomicsPolicy (apps/backend). */
export const ServiceMonetizationMode = Object.freeze({
  VENDOR_SHARE: "vendor_share",
  SERVICE_CHARGE: "service_charge",
});

/* Django routes on port 4610. packages/sdk-client sends these.
   Auth paths stay in apps/backend/auth/contract.py and are not listed here. */
export const HubPath = Object.freeze({
  PARKPE_SESSION_INITIATE: "/api/v1/parkpe/sessions/initiate",
  PARKPE_SESSIONS: "/api/v1/parkpe/sessions",
  PARKPE_VEHICLES: "/api/v1/parkpe/vehicles",
  PAYSWAP_ENTITLEMENTS: "/api/v1/payswap/entitlements",
  PAYSWAP_WALLET: "/api/v1/payswap/wallet",
  PAYSWAP_WALLET_TOPUP: "/api/v1/payswap/wallet/topup-request",
  PAYSWAP_WALLET_PIN: "/api/v1/payswap/wallet/pin",
  PAYSWAP_PG_ORDER: "/api/v1/payswap/pg/order",
  PAYSWAP_PG_VERIFY: "/api/v1/payswap/pg/verify",
  PAYSWAP_TRANSACTIONS: "/api/v1/payswap/transactions",
  PAYSWAP_VOUCHER_ORDER: "/api/v1/payswap/vouchers/order",
  PAYSWAP_BBPS_OPERATORS: "/api/v1/payswap/bbps/operators",
  PAYSWAP_BBPS_CIRCLES: "/api/v1/payswap/bbps/circles",
  PAYSWAP_BBPS_PLANS: "/api/v1/payswap/bbps/plans",
  PAYSWAP_BBPS_FETCH_BILL: "/api/v1/payswap/bbps/fetch-bill",
  PAYSWAP_BBPS_PAY: "/api/v1/payswap/bbps/pay",
  PAYSWAP_BBPS_STATUS: "/api/v1/payswap/bbps/status",
  PAYSWAP_BBPS_BULK_TEMPLATE: "/api/v1/payswap/bbps/bulk/template",
  PAYSWAP_BBPS_BULK_BATCHES: "/api/v1/payswap/bbps/bulk/batches",
  PAYSWAP_COMMISSION_SUMMARY: "/api/v1/payswap/commission/summary",
  PAYSWAP_TDS_CERTIFICATE: "/api/v1/payswap/tds/certificate",
  DESK_ECONOMICS_POLICY: "/api/v1/desk/commission/policy",
  DESK_ECONOMICS_RATES: "/api/v1/desk/commission/rates",
  DESK_ECONOMICS_REVENUE: "/api/v1/desk/commission/revenue",
});
