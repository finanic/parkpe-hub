/* ParkPe hub calls for apps/parkpe/dashboard/index.html.

   Loads packages/sdk-client with X-App-Context: parkpe (packages/contracts
   AppContext.PARKPE). The client sends Idempotency-Key and X-Request-Id
   for apps/backend/core/actions.py. Session start goes through features/qr-connect.
   Does not load apps/payswap/js/session.js. Port 4600 sign-in is separate.
*/

import { AppContext, HubPath } from "../packages/contracts/index.js";
import { createClient } from "../packages/sdk-client/index.js";
import { initiateSession } from "../features/qr-connect/index.js";

const client = createClient(AppContext.PARKPE);

globalThis.ParkpeHub = Object.freeze({
  initiateSession(body, idempotencyKey) {
    return initiateSession(body, idempotencyKey, client);
  },
  vehicles() {
    return client.request(HubPath.PARKPE_VEHICLES, { method: "GET" });
  },
  addVehicle(body, idempotencyKey) {
    return client.request(HubPath.PARKPE_VEHICLES, {
      method: "POST",
      body,
      idempotencyKey: idempotencyKey || crypto.randomUUID(),
    });
  },
  deleteVehicle(id, idempotencyKey) {
    return client.request(`${HubPath.PARKPE_VEHICLES}?vehicle_id=${encodeURIComponent(id)}`, {
      method: "DELETE",
      idempotencyKey: idempotencyKey || crypto.randomUUID(),
    });
  },
  sessions() {
    return client.request(HubPath.PARKPE_SESSIONS, { method: "GET" });
  },
});
