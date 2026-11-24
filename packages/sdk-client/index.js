/* Shared API client for apps/parkpe and apps/payswap.

   Every request sets X-App-Context, which apps/backend/api/v1/deps.py reads
   (parkpe vs payswap). Role still comes from packages/contracts and is checked
   by the API: customer for ParkPe, retailer for PaySwap.

   The client that runs today is apps/payswap/js/session.js. It posts to
   http://127.0.0.1:4600 (apps/backend/auth/server.py) with X-Auth-Request and
   credentials: "include". This module does not replace that call and does
   not send a token of its own. apps/parkpe/ has no auth client yet.
*/

import { AppContext } from "../contracts/index.js";

export const APP_CONTEXT_HEADER = "X-App-Context";

/* Mutating calls such as POST /api/v1/parkpe/sessions/initiate and
   POST /api/v1/payswap/vouchers/order. apps/backend/core/idempotency.py
   rejects the call when this header is missing, and returns 409 when the
   same key is sent with a different body. */
export const IDEMPOTENCY_HEADER = "Idempotency-Key";

export function createClient(appContext, idempotencyKey) {
  if (appContext !== AppContext.PARKPE && appContext !== AppContext.PAYSWAP) {
    throw new Error("app context must be parkpe or payswap");
  }
  const headers = { [APP_CONTEXT_HEADER]: appContext };
  if (idempotencyKey) {
    headers[IDEMPOTENCY_HEADER] = idempotencyKey;
  }
  return Object.freeze({
    appContext,
    headers,
  });
}
