/* Customer session for ParkPe.

   Consumes apps/backend/auth/contract.py Paths and HEADER.
   The role string is packages/contracts Role.CUSTOMER, the same spelling
   as ROLE_CUSTOMER. Paths are not copied into that package.
   Calls http://127.0.0.1:4600 with X-Auth-Request.
   Account creation stays on apps/backend/auth/console/console.js.
   AuthApp._require_operator rejects this origin, so startSignup from
   apps/parkpe/js/screens.js does not open an account here.
   PaySwap (apps/payswap/js/session.js) must not be loaded here.
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

window.ParkpeSession = {
  current() {
    return call("/api/auth/me");
  },
  startSignup(email, mobile, password) {
    return call("/api/auth/signup/start", { email, mobile, password, role: Role.CUSTOMER });
  },
  confirmContact(signupId, emailCode, smsCode) {
    return call("/api/auth/signup/contact", {
      signup_id: signupId,
      email_code: emailCode,
      sms_code: smsCode,
    });
  },
  login(email, password) {
    return call("/api/auth/login", { email, password, role: Role.CUSTOMER });
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
