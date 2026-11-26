/* PaySwap hub calls for apps/payswap/index.html.

   Loads packages/sdk-client with X-App-Context: payswap (packages/contracts
   AppContext.PAYSWAP). The client sends Idempotency-Key and X-Request-Id
   for apps/backend/core/actions.py.
*/

import { AppContext, HubPath } from "../packages/contracts/index.js";
import { createClient } from "../packages/sdk-client/index.js";
import {
  fetchBbpsBill,
  getBbpsStatus,
  listBbpsCircles,
  listBbpsOperators,
  listBbpsPlans,
  payBbpsBill,
} from "../features/bbps/index.js";
import { orderVoucher } from "../features/vouchers/index.js";

const client = createClient(AppContext.PAYSWAP);

globalThis.PayswapHub = Object.freeze({
  entitlements() {
    return client.request(HubPath.PAYSWAP_ENTITLEMENTS, { method: "GET" });
  },
  wallet() {
    return client.request(HubPath.PAYSWAP_WALLET, { method: "GET" });
  },
  tdsCertificate() {
    return client.request(HubPath.PAYSWAP_TDS_CERTIFICATE, { method: "GET" });
  },
  submitTdsCertificate(body) {
    return client.request(HubPath.PAYSWAP_TDS_CERTIFICATE, { method: "POST", body });
  },
  commissionSummary(params = {}) {
    const qs = new URLSearchParams();
    if (params.month) qs.set("month", String(params.month));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return client.request(HubPath.PAYSWAP_COMMISSION_SUMMARY + suffix, { method: "GET" });
  },
  submitTopup(body, idempotencyKey) {
    return client.request(HubPath.PAYSWAP_WALLET_TOPUP, {
      method: "POST",
      body,
      idempotencyKey,
    });
  },
  setWalletPin(body) {
    return client.request(HubPath.PAYSWAP_WALLET_PIN, {
      method: "POST",
      body,
    });
  },
  createPgOrder(body, idempotencyKey) {
    return client.request(HubPath.PAYSWAP_PG_ORDER, {
      method: "POST",
      body,
      idempotencyKey,
    });
  },
  verifyPgOrder(pgOrderId) {
    return client.request(HubPath.PAYSWAP_PG_VERIFY, {
      method: "POST",
      body: { pg_order_id: pgOrderId },
    });
  },
  transactions(params = {}) {
    const qs = new URLSearchParams();
    if (params.service) qs.set("service", String(params.service));
    if (params.state) qs.set("state", String(params.state));
    if (params.q) qs.set("q", String(params.q));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return client.request(HubPath.PAYSWAP_TRANSACTIONS + suffix, { method: "GET" });
  },
  orderVoucher(body, idempotencyKey) {
    return orderVoucher(body, idempotencyKey, client);
  },
  bbpsOperators(params) {
    return listBbpsOperators(params, client);
  },
  bbpsCircles() {
    return listBbpsCircles(client);
  },
  bbpsPlans(params) {
    return listBbpsPlans(params, client);
  },
  fetchBbpsBill(body, idempotencyKey) {
    return fetchBbpsBill(body, idempotencyKey, client);
  },
  payBbpsBill(body, idempotencyKey) {
    return payBbpsBill(body, idempotencyKey, client);
  },
  bbpsStatus(reference) {
    return getBbpsStatus(reference, client);
  },
});
