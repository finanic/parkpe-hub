/* Backend operator console.

   Served by auth.server._console from this same process.
   Calls the routes in auth.contract.Paths with role "operator".
   Payswap and ParkPe do not load this file.
*/
(function () {
  const ROLE = "operator";

  async function call(path, payload) {
    const headers = { "X-Auth-Request": "1" };
    const init = { method: "GET", credentials: "same-origin", headers };
    if (payload !== undefined) {
      init.method = "POST";
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(payload);
    }
    try {
      const response = await fetch(path, init);
      const data = await response.json().catch(() => ({}));
      return { ok: response.ok, status: response.status, data };
    } catch (error) {
      return { ok: false, status: 0, data: { error: "Auth service is not reachable." } };
    }
  }

  function show(name) {
    document.querySelectorAll("[data-view]").forEach((node) => {
      node.hidden = node.dataset.view !== name;
    });
  }

  function error(form, message) {
    const node = form.querySelector("[data-error]");
    node.hidden = !message;
    node.textContent = message || "";
  }

  function enter(user) {
    document.getElementById("who").textContent = user.email + " · " + user.role;
    show("home");
  }

  document.addEventListener("click", (event) => {
    const reveal = event.target.closest("[data-reveal]");
    if (reveal) {
      const input = reveal.parentElement.querySelector("input");
      const shown = input.type === "text";
      input.type = shown ? "password" : "text";
      reveal.textContent = shown ? "Show" : "Hide";
      reveal.setAttribute("aria-label", shown ? "Show password" : "Hide password");
      return;
    }
    const next = event.target.closest("[data-show]");
    if (next) show(next.dataset.show);
  });

  document.getElementById("login").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    error(form, "");
    const result = await call("/api/auth/login", {
      email: form.email.value,
      password: form.password.value,
      role: ROLE,
    });
    if (result.data.mfa_required) return show("mfa");
    if (result.data.mfa_setup_required) return show("enroll");
    if (result.ok) return enter(result.data);
    error(form, result.data.error || "Sign-in failed.");
  });

  document.getElementById("register").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    error(form, "");
    const created = await call("/api/auth/register", {
      email: form.email.value,
      password: form.password.value,
      role: ROLE,
    });
    if (!created.ok) return error(form, created.data.error || "Could not create the operator.");
    const result = await call("/api/auth/login", {
      email: form.email.value,
      password: form.password.value,
      role: ROLE,
    });
    if (result.data.mfa_setup_required) return show("enroll");
    if (result.data.mfa_required) return show("mfa");
    error(form, result.data.error || "Account saved. Sign in with the existing password.");
  });

  document.getElementById("mfa").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    error(form, "");
    const result = await call("/api/auth/mfa", { code: form.code.value });
    if (result.ok) return enter(result.data);
    error(form, result.data.error || "Code is incorrect.");
  });

  document.getElementById("start-enroll").addEventListener("click", async () => {
    const result = await call("/api/auth/mfa/setup", {});
    if (!result.ok) return error(document.getElementById("enroll-confirm"), result.data.error || "Could not start setup.");
    const secret = document.querySelector("[data-secret]");
    const codes = document.querySelector("[data-codes]");
    secret.hidden = false;
    secret.textContent = result.data.secret;
    document.querySelector("[data-secret-label]").hidden = false;
    codes.hidden = false;
    codes.textContent = result.data.backup_codes.join("  ");
    document.querySelector("[data-codes-label]").hidden = false;
  });

  document.getElementById("enroll-confirm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    error(form, "");
    const result = await call("/api/auth/mfa/confirm", { code: form.code.value });
    if (result.ok) return enter(result.data);
    error(form, result.data.error || "Code is incorrect.");
  });

  document.getElementById("logout").addEventListener("click", async () => {
    await call("/api/auth/logout", {});
    show("login");
  });

  Promise.all([call("/api/auth/me"), call("/api/auth/setup")]).then(([me, setup]) => {
    const create = document.querySelector("[data-show='register']");
    if (setup.data.signup_open) create.hidden = false;
    if (me.ok && me.data.role === ROLE) enter(me.data);
    else if (me.status === 403 && me.data.mfa_setup_required && me.data.role === ROLE) show("enroll");
    else show("login");
  });
})();
