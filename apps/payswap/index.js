/* PaySwap app barrel. Re-exports core/, shared/, and features/.

   The page that calls Django is apps/payswap/js/hub.js, with
   X-App-Context: payswap through packages/sdk-client.
   POST /api/v1/payswap/vouchers/order is apps/backend/api/v1/routes/payswap.py.
   Sign-in stays in apps/payswap/js/session.js on port 4600.
   DTOs: packages/contracts. Tokens: packages/ui-tokens.
   Does not import apps/parkpe or apps/parkpe/js/screens.js.
   apps/payswap/serve.py serves this folder.
*/

export { core } from "./core/index.js";
export { shared } from "./shared/index.js";
export { features } from "./features/index.js";
