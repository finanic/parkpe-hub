/* PaySwap hub calls for apps/payswap/index.html.

   Loads packages/sdk-client with X-App-Context: payswap (packages/contracts
   AppContext.PAYSWAP). The client sends Idempotency-Key and X-Request-Id
   for apps/backend/core/actions.py.
*/

import { AppContext, HubPath } from "../packages/contracts/index.js";
import { createClient, saveBlob } from "../packages/sdk-client/index.js";
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
  initiatePayu(orderId) {
    return client.request("/api/payu/initiate", {
      method: "POST",
      body: { order_id: orderId },
    });
  },
  verifyPayu(orderId) {
    return client.request("/api/payu/verify/" + encodeURIComponent(orderId), { method: "GET" });
  },
  verifyPgOrder(pgOrderId, idempotencyKey) {
    return client.request(HubPath.PAYSWAP_PG_VERIFY, {
      method: "POST",
      body: { pg_order_id: pgOrderId },
      idempotencyKey: idempotencyKey || (globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : `pgv-${Date.now()}`),
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
  bulkBbpsTemplateUrl(params = {}) {
    const qs = new URLSearchParams();
    // Multi-biller sheet: plan=65:3,99:2 — GET so sdk-client download works (X-App-Context + cookies).
    if (Array.isArray(params.billers) && params.billers.length) {
      const plan = params.billers
        .map((row) => {
          const op = String((row && (row.op || row.biller_id)) || "").trim();
          const count = Math.max(1, Math.min(500, Number(row && row.count) || 1));
          return op ? `${op}:${count}` : "";
        })
        .filter(Boolean)
        .join(",");
      if (plan) qs.set("plan", plan);
    } else {
      if (params.op) qs.set("op", String(params.op));
      if (params.biller_id) qs.set("biller_id", String(params.biller_id));
      if (params.plan) qs.set("plan", String(params.plan));
    }
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return `${HubPath.PAYSWAP_BBPS_BULK_TEMPLATE}${suffix}`;
  },
  async downloadBulkBbpsTemplate(params = {}) {
    const billers = Array.isArray(params.billers) ? params.billers : null;
    const path = this.bulkBbpsTemplateUrl(params);
    let fallbackName = "payswap-bulk-bbps-template.csv";
    if (billers && billers.length === 1) {
      fallbackName = `bulk-${billers[0].op || billers[0].biller_id || "biller"}.csv`;
    } else if (billers && billers.length > 1) {
      fallbackName = `bulk-${billers.length}-billers.csv`;
    } else {
      const op = String(params.op || params.biller_id || "").trim();
      if (op) fallbackName = `bulk-${op}.csv`;
    }
    // Accept */* so error JSON still parses when a biller/plan fails validation.
    const res = await client.download(path, {
      filename: fallbackName,
      accept: "*/*",
    });
    if (res.ok && res.blob) saveBlob(res.blob, res.filename || fallbackName);
    return res;
  },
  async downloadBulkBbpsExport(batchId) {
    const path = `${HubPath.PAYSWAP_BBPS_BULK_BATCHES}/${encodeURIComponent(batchId)}/export`;
    const res = await client.download(path, {
      filename: `bulk-bbps-${batchId}.csv`,
      accept: "text/csv,*/*",
    });
    if (res.ok && res.blob) saveBlob(res.blob, res.filename || `bulk-bbps-${batchId}.csv`);
    return res;
  },
  bulkBbpsBatches() {
    return client.request(HubPath.PAYSWAP_BBPS_BULK_BATCHES, { method: "GET" });
  },
  bulkBbpsBatch(batchId) {
    return client.request(`${HubPath.PAYSWAP_BBPS_BULK_BATCHES}/${encodeURIComponent(batchId)}`, { method: "GET" });
  },
  bulkBbpsRows(batchId, params = {}) {
    const qs = new URLSearchParams();
    if (params.fetch_state) qs.set("fetch_state", String(params.fetch_state));
    if (params.pay_state) qs.set("pay_state", String(params.pay_state));
    if (params.due_bucket) qs.set("due_bucket", String(params.due_bucket));
    if (params.q) qs.set("q", String(params.q));
    if (params.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return client.request(
      `${HubPath.PAYSWAP_BBPS_BULK_BATCHES}/${encodeURIComponent(batchId)}/rows${suffix}`,
      { method: "GET" }
    );
  },
  uploadBulkBbps(file, options = {}) {
    const formData = new FormData();
    formData.append("file", file);
    const op = String(options.op || options.operator_id || "").trim();
    const billerId = String(options.biller_id || "").trim();
    if (op) formData.append("op", op);
    if (billerId) formData.append("biller_id", billerId);
    return client.request(HubPath.PAYSWAP_BBPS_BULK_BATCHES, {
      method: "POST",
      formData,
      idempotencyKey:
        options.idempotencyKey ||
        (globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : `bulk-up-${Date.now()}`),
    });
  },
  refetchBulkBbps(batchId, body = {}) {
    return client.request(`${HubPath.PAYSWAP_BBPS_BULK_BATCHES}/${encodeURIComponent(batchId)}/refetch`, {
      method: "POST",
      body,
      idempotencyKey: globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : `bulk-refetch-${Date.now()}`,
    });
  },
  proceedBulkBbps(batchId, body, idempotencyKey) {
    return client.request(`${HubPath.PAYSWAP_BBPS_BULK_BATCHES}/${encodeURIComponent(batchId)}/proceed`, {
      method: "POST",
      body,
      idempotencyKey:
        idempotencyKey ||
        (globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : `bulk-pay-${Date.now()}`),
    });
  },
  cancelBulkBbps(batchId) {
    return client.request(`${HubPath.PAYSWAP_BBPS_BULK_BATCHES}/${encodeURIComponent(batchId)}/cancel`, {
      method: "POST",
      body: {},
      idempotencyKey: globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : `bulk-cancel-${Date.now()}`,
    });
  },
  bulkBbpsExportUrl(batchId) {
    return `${HubPath.PAYSWAP_BBPS_BULK_BATCHES}/${encodeURIComponent(batchId)}/export`;
  },
});
