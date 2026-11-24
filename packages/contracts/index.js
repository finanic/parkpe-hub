/* Shared DTOs, enums, and error codes.

   Consumers: apps/parkpe, apps/payswap, packages/sdk-client,
   and apps/backend/schemas (same field names).
   Live constants that already ship: apps/backend/auth/contract.py
   (Paths, cookies, ROLE_CUSTOMER, ROLE_RETAILER, ROLE_OPERATOR, X-Auth-Request).
   Do not copy those into either frontend.
*/

export const AppContext = Object.freeze({
  PARKPE: "parkpe",
  PAYSWAP: "payswap",
});

export const Role = Object.freeze({
  CUSTOMER: "customer",
  RETAILER: "retailer",
  OPERATOR: "operator",
});

export const ErrorCode = Object.freeze({
  UNAUTHENTICATED: "unauthenticated",
  FORBIDDEN_APP: "forbidden_app",
  VALIDATION: "validation",
  IDEMPOTENCY_CONFLICT: "idempotency_conflict",
  SERVER_ERROR: "server_error",
});

/* Django routes on port 4610. packages/sdk-client sends these.
   Auth paths stay in apps/backend/auth/contract.py and are not listed here. */
export const HubPath = Object.freeze({
  PARKPE_SESSION_INITIATE: "/api/v1/parkpe/sessions/initiate",
  PAYSWAP_VOUCHER_ORDER: "/api/v1/payswap/vouchers/order",
});
