/* PaySwap app barrel.

   Mounts core/, shared/, and features/ (cards, vouchers, bbps, transactions).
   Calls apps/backend through packages/sdk-client with X-App-Context: payswap.
   DTOs: packages/contracts. Tokens: packages/ui-tokens.
   Does not import apps/parkpe or apps/parkpe/js/screens.js.
   apps/payswap/serve.py does not load this file. Live client: apps/payswap/js/session.js.
*/

export { core } from "./core/index.js";
export { shared } from "./shared/index.js";
export { features } from "./features/index.js";
