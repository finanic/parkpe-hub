/* Retailer session for the PaySwap counter.

   Consumes apps/backend/auth/contract.py Paths and HEADER.
   The role string is packages/contracts Role.RETAILER, the same spelling
   as ROLE_RETAILER. Paths are not copied into that package.
   Every call hits http://127.0.0.1:4600 with X-Auth-Request.
   Retailer creation stays on apps/backend/auth/console/console.js.
   AuthApp._require_operator rejects this origin.
   ParkPe must not load this file.
*/

import { Role } from "../packages/contracts/index.js";

const API = "http://127.0.0.1:4600";

async function call(path, payload) {
  const headers = { "X-Auth-Request": "1" };
  const init = { method: "GET", credentials: "include", headers };
  if (payload !== undefined) {
    init.method = "POST";
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(payload);
  }
  try {
    const response = await fetch(API + path, init);
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, status: response.status, data };
  } catch (error) {
    return { ok: false, status: 0, data: { error: "Sign-in service is not reachable." } };
  }
}

window.PayswapSession = {
  current() {
    return call("/api/auth/me");
  },
  login(email, password) {
    return call("/api/auth/login", { email, password, role: Role.RETAILER });
  },
  confirmCode(code) {
    return call("/api/auth/mfa", { code });
  },
  beginAuthenticator() {
    return call("/api/auth/mfa/setup", {});
  },
  enableAuthenticator(code) {
    return call("/api/auth/mfa/confirm", { code });
  },
  signOut() {
    return call("/api/auth/logout", {});
  },
};
