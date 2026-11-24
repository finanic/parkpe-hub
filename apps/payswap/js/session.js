/* Retailer session for the PaySwap counter.

   Consumes apps/backend/auth/contract.py. Every call hits http://127.0.0.1:4600
   with X-Auth-Request and credentials so the HttpOnly cookies stick.
   Role is fixed to retailer. ParkPe must not load this file.
*/
(function () {
  const API = "http://127.0.0.1:4600";
  const ROLE = "retailer";

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
    register(email, password) {
      return call("/api/auth/register", { email, password, role: ROLE });
    },
    login(email, password) {
      return call("/api/auth/login", { email, password, role: ROLE });
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
})();
