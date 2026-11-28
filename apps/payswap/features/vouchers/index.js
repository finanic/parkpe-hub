/* Brand voucher order for apps/payswap.

   Live screen: vouchers() in apps/payswap/js/services.js. The page loads
   apps/payswap/js/hub.js, which calls orderVoucher here.
   POST HubPath.PAYSWAP_VOUCHER_ORDER through packages/sdk-client
   (X-App-Context: payswap, Idempotency-Key, X-Request-Id) to
   apps/backend/api/v1/routes/payswap.py. The result line is core/actions.py.
   Sign-in stays in apps/payswap/js/session.js on port 4600.
*/

import { AppContext } from "../../../../packages/contracts/index.js";
import { HubPath, createClient } from "../../../../packages/sdk-client/index.js";

export const vouchers = Object.freeze({ id: "vouchers" });

export function orderVoucher(body, idempotencyKey, client = createClient(AppContext.PAYSWAP), requestId) {
  return client.request(HubPath.PAYSWAP_VOUCHER_ORDER, {
    method: "POST",
    body,
    idempotencyKey,
    requestId,
  });
}
