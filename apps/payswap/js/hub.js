/* PaySwap hub calls for apps/payswap/index.html.

   Loads packages/sdk-client with X-App-Context: payswap (packages/contracts
   AppContext.PAYSWAP). Voucher orders go through features/vouchers.
   apps/payswap/js/session.js still signs in on port 4600 with role retailer.
   ParkPe must not load this file.
*/

import { AppContext } from "../packages/contracts/index.js";
import { createClient } from "../packages/sdk-client/index.js";
import { orderVoucher } from "../features/vouchers/index.js";

const client = createClient(AppContext.PAYSWAP);

globalThis.PayswapHub = Object.freeze({
  orderVoucher(body, idempotencyKey) {
    return orderVoucher(body, idempotencyKey, client);
  },
});
