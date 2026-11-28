/* QR session for apps/parkpe.

   Live screen: qrScreen in apps/parkpe/js/screens.js. The page loads
   apps/parkpe/js/hub.js, which calls initiateSession here.
   POST HubPath.PARKPE_SESSION_INITIATE through packages/sdk-client
   (X-App-Context: parkpe, Idempotency-Key, X-Request-Id) to
   apps/backend/api/v1/routes/parkpe.py. The result line is core/actions.py.
*/

import { AppContext } from "../../../../packages/contracts/index.js";
import { HubPath, createClient } from "../../../../packages/sdk-client/index.js";

export const qrConnect = Object.freeze({ id: "qr-connect" });

export function initiateSession(body, idempotencyKey, client = createClient(AppContext.PARKPE), requestId) {
  return client.request(HubPath.PARKPE_SESSION_INITIATE, {
    method: "POST",
    body,
    idempotencyKey,
    requestId,
  });
}
