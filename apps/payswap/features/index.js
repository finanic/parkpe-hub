/* PaySwap features. Each folder owns one product area and calls
   apps/backend/domain/payswap through packages/sdk-client.
   Do not import apps/parkpe/features.
*/

import { cards } from "./cards/index.js";
import { vouchers } from "./vouchers/index.js";
import { bbps } from "./bbps/index.js";
import { transactions } from "./transactions/index.js";

export { cards, vouchers, bbps, transactions };

export const features = Object.freeze({ cards, vouchers, bbps, transactions });
