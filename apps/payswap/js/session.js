/* Retailer session for the PaySwap counter.

   Consumes apps/backend/auth/contract.py Paths and HEADER.
   The role string is packages/contracts Role.RETAILER, the same spelling
   as ROLE_RETAILER. Paths are not copied into that package.
   Every call hits http://127.0.0.1:4600 with X-Auth-Request.
   Retailer creation stays on apps/backend/auth/console/console.js.
   ParkPe must not load this file.

   device_id is a stable browser id (localStorage). Auth binds one login
   family per device so refresh/re-login on the same browser does not
   stack duplicate sessions in Profile.
*/

import { Role } from "../packages/contracts/index.js";

const API = "http://127.0.0.1:4600";
const DEVICE_KEY = "payswap-device-id";

function deviceId() {
  try {
    let id = localStorage.getItem(DEVICE_KEY);
    if (id && id.length >= 16) return id;
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      id = crypto.randomUUID();
    } else if (typeof crypto !== "undefined" && crypto.getRandomValues) {
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      id = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    } else {
      throw new Error("secure random unavailable");
    }
    localStorage.setItem(DEVICE_KEY, id);
    return id;
  } catch (_err) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) {
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      return `ps-ephemeral-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
    }
    return "ps-ephemeral-unavailable";
  }
}

async function call(path, payload) {
  const headers = { "X-Auth-Request": "1" };
  const init = { method: "GET", credentials: "include", headers };
  if (payload !== undefined) {
    init.method = "POST";
    headers["Content-Type"] = "application/json";
    const body = { ...payload, device_id: deviceId() };
    init.body = JSON.stringify(body);
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
  deviceId,
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
  profile() {
    return call("/api/auth/profile");
  },
  updateProfile(body) {
    return call("/api/auth/profile", body);
  },
  changePassword(body) {
    return call("/api/auth/password/change", body);
  },
  sessions() {
    return call("/api/auth/sessions");
  },
  revokeOtherSessions() {
    return call("/api/auth/sessions/revoke", {});
  },
};
