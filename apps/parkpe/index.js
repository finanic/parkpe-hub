/* ParkPe app barrel.

   Mounts core/, shared/, and features/ (parking, fastag, carpool, qr-connect).
   Calls apps/backend through packages/sdk-client with X-App-Context: parkpe.
   DTOs: packages/contracts. Tokens: packages/ui-tokens.
   Does not import apps/payswap or apps/payswap/js/session.js.
   apps/parkpe/serve.py does not load this file. Live screens: apps/parkpe/js/screens.js.
*/

export { core } from "./core/index.js";
export { shared } from "./shared/index.js";
export { features } from "./features/index.js";
