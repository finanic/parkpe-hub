/* PaySwap features. Each folder owns one product area.
   vouchers calls packages/sdk-client (X-App-Context: payswap).
   Cards, BBPS, and the transaction list are still local screens.
   Do not import apps/parkpe/features.
*/

import { cards } from "./cards/index.js";
import { orderVoucher, vouchers } from "./vouchers/index.js";
import { bbps } from "./bbps/index.js";
import { transactions } from "./transactions/index.js";

export { cards, vouchers, bbps, transactions, orderVoucher };

export const features = Object.freeze({ cards, vouchers, bbps, transactions, orderVoucher });
