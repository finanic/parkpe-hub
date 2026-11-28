/* Shared API client for apps/parkpe and apps/payswap.

   Every request sets X-App-Context, which apps/backend/api/v1/deps.py reads
   (parkpe vs payswap). Role still comes from packages/contracts and is checked
   by the API: customer for ParkPe, retailer for PaySwap.

   request() posts to http://127.0.0.1:4610. Paths are HubPath in
   packages/contracts/index.js. POST, PUT, and PATCH send Idempotency-Key.
   apps/backend/core/idempotency.py stores the response and returns 409 when
   the same key is reused with a different body. A safe X-Request-Id is sent
   when the caller passed one or crypto.randomUUID exists. config/request.py
   copies that value into core/actions.py. Failures always return error and code.

   The retailer sign-in that runs today is apps/payswap/js/session.js. It posts
   to http://127.0.0.1:4600 (apps/backend/auth/server.py) with X-Auth-Request.
   This module does not replace that call. Live hub callers:
   apps/parkpe/js/hub.js and apps/payswap/js/hub.js.
*/

import { AppContext, ErrorCode, HubPath } from "../contracts/index.js";

export const APP_CONTEXT_HEADER = "X-App-Context";
export const IDEMPOTENCY_HEADER = "Idempotency-Key";
export const REQUEST_ID_HEADER = "X-Request-Id";
export const HUB_ORIGIN = "http://127.0.0.1:4610";

const MUTATING = new Set(["POST", "PUT", "PATCH"]);
const REQUEST_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,79}$/;

export function createClient(appContext, idempotencyKey) {
  if (appContext !== AppContext.PARKPE && appContext !== AppContext.PAYSWAP) {
    throw new Error("app context must be parkpe or payswap");
  }
  const headers = { [APP_CONTEXT_HEADER]: appContext };
  if (idempotencyKey) {
    headers[IDEMPOTENCY_HEADER] = idempotencyKey;
  }
  return Object.freeze({
    appContext,
    headers,
    request(path, options = {}) {
      return send(appContext, idempotencyKey, path, options);
    },
    download(path, options = {}) {
      return downloadFile(appContext, path, options);
    },
  });
}

async function send(appContext, defaultKey, path, options) {
  const method = String(options.method || "GET").toUpperCase();
  const requestId = availableRequestId(options.requestId);
  const headers = {
    Accept: "application/json",
    [APP_CONTEXT_HEADER]: appContext,
  };
  if (requestId) headers[REQUEST_ID_HEADER] = requestId;
  const init = { method, headers, credentials: "include" };
  if (MUTATING.has(method)) {
    const key = options.idempotencyKey || defaultKey || "";
    if (!key || String(key).trim() !== String(key) || /\s/.test(String(key))) {
      return failure(400, "Send an Idempotency-Key.", ErrorCode.VALIDATION, requestId);
    }
    headers[IDEMPOTENCY_HEADER] = String(key);
    if (options.formData instanceof FormData) {
      // Browser sets multipart boundary; do not force application/json.
      init.body = options.formData;
    } else {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body ?? {});
    }
  }
  const doFetch = options.fetch || globalThis.fetch;
  let response;
  try {
    response = await doFetch(HUB_ORIGIN + path, init);
  } catch {
    return failure(0, "The hub API is not reachable.", ErrorCode.SERVER_ERROR, requestId);
  }
  let payload = {};
  try {
    const parsed = await response.json();
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) payload = parsed;
  } catch {
    payload = {};
  }
  if (response.ok) {
    return { ok: true, status: response.status, data: payload, error: "", code: "", requestId };
  }
  const error = typeof payload.error === "string" && payload.error ? payload.error : "Check the request.";
  const code = typeof payload.code === "string" && payload.code ? payload.code : codeForStatus(response.status);
  return { ok: false, status: response.status, data: payload, error, code, requestId };
}

function availableRequestId(given) {
  if (typeof given === "string" && REQUEST_ID.test(given)) return given;
  const cryptoObj = globalThis.crypto;
  if (cryptoObj && typeof cryptoObj.randomUUID === "function") {
    const minted = cryptoObj.randomUUID();
    if (REQUEST_ID.test(minted)) return minted;
  }
  return "";
}

/* File GETs (CSV template/export) need X-App-Context + cookies; window.open cannot set the header. */
async function downloadFile(appContext, path, options = {}) {
  const requestId = availableRequestId(options.requestId);
  const headers = {
    Accept: options.accept || "*/*",
    [APP_CONTEXT_HEADER]: appContext,
  };
  if (requestId) headers[REQUEST_ID_HEADER] = requestId;
  const doFetch = options.fetch || globalThis.fetch;
  let response;
  try {
    response = await doFetch(HUB_ORIGIN + path, { method: "GET", headers, credentials: "include" });
  } catch {
    return failure(0, "The hub API is not reachable.", ErrorCode.SERVER_ERROR, requestId);
  }
  if (!response.ok) {
    let payload = {};
    try {
      const parsed = await response.json();
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) payload = parsed;
    } catch {
      payload = {};
    }
    const error = typeof payload.error === "string" && payload.error ? payload.error : "Download failed.";
    const code = typeof payload.code === "string" && payload.code ? payload.code : codeForStatus(response.status);
    return { ok: false, status: response.status, data: payload, error, code, requestId, blob: null, filename: "" };
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^\";]+)/i);
  const filename = (match && decodeURIComponent(match[1].replace(/"/g, ""))) || options.filename || "download.bin";
  return { ok: true, status: response.status, data: {}, error: "", code: "", requestId, blob, filename };
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "download.bin";
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function failure(status, error, code, requestId = "") {
  return { ok: false, status, data: {}, error, code, requestId };
}

function codeForStatus(status) {
  if (status === 401) return ErrorCode.UNAUTHENTICATED;
  if (status === 403) return ErrorCode.FORBIDDEN_APP;
  if (status === 409) return ErrorCode.IDEMPOTENCY_CONFLICT;
  if (status >= 500 || status === 0) return ErrorCode.SERVER_ERROR;
  return ErrorCode.VALIDATION;
}

export { HubPath, saveBlob };
