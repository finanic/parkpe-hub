/* ParkPe app barrel. Re-exports core/, shared/, and features/.

   The page that calls Django is apps/parkpe/js/hub.js, with
   X-App-Context: parkpe through packages/sdk-client.
   POST /api/v1/parkpe/sessions/initiate is apps/backend/api/v1/routes/parkpe.py.
   DTOs: packages/contracts. Tokens: packages/ui-tokens.
   Does not import apps/payswap or apps/payswap/js/session.js.
   apps/parkpe/serve.py serves this folder. Live screens: apps/parkpe/js/screens.js.
*/

export { core } from "./core/index.js";
export { shared } from "./shared/index.js";
export { features } from "./features/index.js";
