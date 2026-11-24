/* Shared API client for apps/parkpe and apps/payswap.

   Every request sets X-App-Context, which apps/backend/api/v1/deps.py reads
   (parkpe vs payswap). Role still comes from packages/contracts and is checked
   by the API: customer for ParkPe, retailer for PaySwap.

   request() posts to http://127.0.0.1:4610. Paths are HubPath in
   packages/contracts/index.js. POST, PUT, and PATCH send Idempotency-Key.
   apps/backend/core/idempotency.py stores the response and returns 409 when
   the same key is reused with a different body.

   The retailer sign-in that runs today is apps/payswap/js/session.js. It posts
   to http://127.0.0.1:4600 (apps/backend/auth/server.py) with X-Auth-Request.
   This module does not replace that call. Live hub callers:
   apps/parkpe/js/hub.js and apps/payswap/js/hub.js.
*/

import { AppContext, ErrorCode, HubPath } from "../contracts/index.js";

export const APP_CONTEXT_HEADER = "X-App-Context";
export const IDEMPOTENCY_HEADER = "Idempotency-Key";
export const HUB_ORIGIN = "http://127.0.0.1:4610";

const MUTATING = new Set(["POST", "PUT", "PATCH"]);

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
  });
}

async function send(appContext, defaultKey, path, options) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = {
    Accept: "application/json",
    [APP_CONTEXT_HEADER]: appContext,
  };
  const init = { method, headers, credentials: "include" };
  if (MUTATING.has(method)) {
    const key = options.idempotencyKey || defaultKey || "";
    if (!key || String(key).trim() !== String(key) || /\s/.test(String(key))) {
      return failure(400, "Send an Idempotency-Key.", ErrorCode.VALIDATION);
    }
    headers["Content-Type"] = "application/json";
    headers[IDEMPOTENCY_HEADER] = String(key);
    init.body = JSON.stringify(options.body ?? {});
  }
  const doFetch = options.fetch || globalThis.fetch;
  let response;
  try {
    response = await doFetch(HUB_ORIGIN + path, init);
  } catch {
    return failure(0, "The hub API is not reachable.", ErrorCode.SERVER_ERROR);
  }
  let payload = {};
  try {
    const parsed = await response.json();
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) payload = parsed;
  } catch {
    payload = {};
  }
  if (response.ok) {
    return { ok: true, status: response.status, data: payload, error: "", code: "" };
  }
  const error = typeof payload.error === "string" && payload.error ? payload.error : "Check the request.";
  const code = typeof payload.code === "string" && payload.code ? payload.code : codeForStatus(response.status);
  return { ok: false, status: response.status, data: payload, error, code };
}

function failure(status, error, code) {
  return { ok: false, status, data: {}, error, code };
}

function codeForStatus(status) {
  if (status === 401) return ErrorCode.UNAUTHENTICATED;
  if (status === 403) return ErrorCode.FORBIDDEN_APP;
  if (status === 409) return ErrorCode.IDEMPOTENCY_CONFLICT;
  if (status >= 500 || status === 0) return ErrorCode.SERVER_ERROR;
  return ErrorCode.VALIDATION;
}

export { HubPath };
