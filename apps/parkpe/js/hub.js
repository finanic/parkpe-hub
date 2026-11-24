/* ParkPe hub calls for apps/parkpe/dashboard/index.html.

   Loads packages/sdk-client with X-App-Context: parkpe (packages/contracts
   AppContext.PARKPE). The client sends Idempotency-Key and X-Request-Id
   for apps/backend/core/actions.py. Session start goes through features/qr-connect.
   Does not load apps/payswap/js/session.js. Port 4600 sign-in is separate.
*/

import { AppContext } from "../packages/contracts/index.js";
import { createClient } from "../packages/sdk-client/index.js";
import { initiateSession } from "../features/qr-connect/index.js";

const client = createClient(AppContext.PARKPE);

globalThis.ParkpeHub = Object.freeze({
  initiateSession(body, idempotencyKey) {
    return initiateSession(body, idempotencyKey, client);
  },
});
