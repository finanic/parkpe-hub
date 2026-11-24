/* Retailer transaction list for apps/payswap.

   Live UI: transactions() in apps/payswap/js/services.js.
   Rows there are local samples (AEPS, DMT, recharge, bills), not apps/backend.
   Future API: apps/backend/domain/payswap. A retry must reuse the idempotency
   key from apps/backend/core/idempotency.py.
*/

export const transactions = Object.freeze({ id: "transactions" });
