/* Mobikwik BBPS bill fetch, payment, and status for apps/payswap.

   Live screen: bills() in apps/payswap/js/services.js. The page loads
   apps/payswap/js/hub.js, which calls these helpers.
   Routes: HubPath.PAYSWAP_BBPS_* in packages/contracts/index.js through
   packages/sdk-client (X-App-Context: payswap, Idempotency-Key, X-Request-Id)
   to apps/backend/api/v1/routes/payswap.py. Sign-in stays in
   apps/payswap/js/session.js on port 4600.
*/

import { AppContext } from "../../../../packages/contracts/index.js";
import { HubPath, createClient } from "../../../../packages/sdk-client/index.js";

export const bbps = Object.freeze({ id: "bbps" });

export function listBbpsOperators(params = {}, client = createClient(AppContext.PAYSWAP)) {
  const qs = new URLSearchParams();
  if (params.category) qs.set("category", String(params.category));
  if (params.q) qs.set("q", String(params.q));
  if (params.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return client.request(HubPath.PAYSWAP_BBPS_OPERATORS + suffix, { method: "GET" });
}

export function listBbpsCircles(client = createClient(AppContext.PAYSWAP)) {
  return client.request(HubPath.PAYSWAP_BBPS_CIRCLES, { method: "GET" });
}

export function listBbpsPlans(params = {}, client = createClient(AppContext.PAYSWAP)) {
  const qs = new URLSearchParams();
  if (params.biller) qs.set("biller", String(params.biller));
  if (params.account) qs.set("account", String(params.account));
  if (params.circle) qs.set("circle", String(params.circle));
  return client.request(`${HubPath.PAYSWAP_BBPS_PLANS}?${qs.toString()}`, { method: "GET" });
}

export function fetchBbpsBill(body, idempotencyKey, client = createClient(AppContext.PAYSWAP), requestId) {
  return client.request(HubPath.PAYSWAP_BBPS_FETCH_BILL, {
    method: "POST",
    body,
    idempotencyKey,
    requestId,
  });
}

export function payBbpsBill(body, idempotencyKey, client = createClient(AppContext.PAYSWAP), requestId) {
  return client.request(HubPath.PAYSWAP_BBPS_PAY, {
    method: "POST",
    body,
    idempotencyKey,
    requestId,
  });
}

export function getBbpsStatus(reference, client = createClient(AppContext.PAYSWAP)) {
  const qs = new URLSearchParams({ reference: String(reference || "") });
  return client.request(`${HubPath.PAYSWAP_BBPS_STATUS}?${qs.toString()}`, { method: "GET" });
}
