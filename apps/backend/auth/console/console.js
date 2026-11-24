/* Backend admin console.

   Served by auth.server._console from this same process.
   Calls the routes in auth.contract.Paths with role "admin".
   Payswap and ParkPe do not load this file.
*/
(function () {
  const ROLE = "admin";

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

  const ROOM_TITLE = {
    overview: "Dashboard",
    people: "People",
    parkpe: "ParkPe",
    payswap: "PaySwap",
    money: "Money",
    verification: "Verification",
    processes: "Processes",
  };

  function show(name) {
    document.querySelectorAll("[data-view]").forEach((node) => {
      node.hidden = node.dataset.view !== name;
    });
    document.getElementById("gate").hidden = name === "home";
  }

  function room(name) {
    document.querySelectorAll("[data-room]").forEach((node) => {
      node.classList.toggle("is-on", node.dataset.room === name);
    });
    document.querySelectorAll("[data-panel]").forEach((node) => {
      node.hidden = node.dataset.panel !== name;
    });
    document.getElementById("crumb").textContent = ROOM_TITLE[name] || "Dashboard";
    document.title = (ROOM_TITLE[name] || "Dashboard") + " · Backend";
    if (name === "people") loadPeople();
    if (name === "verification") loadSignups();
    if (name === "processes") loadProcesses();
  }

  function fillList(selector, rows, empty) {
    const list = document.querySelector(selector);
    list.replaceChildren();
    if (!rows.length) {
      const item = document.createElement("li");
      item.textContent = empty;
      list.appendChild(item);
      return list;
    }
    return list;
  }

  function error(form, message) {
    const node = form.querySelector("[data-error]");
    node.hidden = !message;
    node.textContent = message || "";
  }

  async function paintDesk(user) {
    const desk = await call("/api/auth/desk");
    const data = desk.ok ? desk.data : {};
    document.getElementById("who").textContent = (data.email || user.email) + " · " + (data.role || user.role);
    const counts = data.counts || {};
    document.querySelectorAll("[data-count]").forEach((node) => {
      node.textContent = String(counts[node.dataset.count] || 0);
    });
    document.querySelector("[data-desk-note]").textContent = data.signup_open
      ? "The first admin account can still be created."
      : "Admin signup is closed. This session has the authenticator on.";
    const list = document.querySelector("[data-events]");
    list.replaceChildren();
    const events = data.events || [];
    if (!events.length) {
      const item = document.createElement("li");
      item.textContent = "No auth events yet.";
      list.appendChild(item);
    } else {
      events.forEach((event) => {
        const item = document.createElement("li");
        const when = new Date(event.at * 1000).toLocaleString("en-IN", {
          day: "2-digit",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        });
        item.textContent = [event.event, event.email, when].filter(Boolean).join(" · ");
        list.appendChild(item);
      });
    }
  }

  async function enter(user) {
    await paintDesk(user);
    show("home");
    room("overview");
  }

  async function loadPeople() {
    const result = await call("/api/auth/desk/people");
    const people = result.ok ? result.data.people || [] : [];
    const list = fillList("[data-people]", people, result.ok ? "No accounts yet." : (result.data.error || "Could not load people."));
    people.forEach((person) => {
      const item = document.createElement("li");
      const line = document.createElement("span");
      const auth = person.authenticator ? "authenticator on" : "authenticator off";
      const door = person.sign_in ? "sign-in open" : "sign-in closed";
      line.textContent = [person.email, (person.roles || []).join(", "), auth, door].filter(Boolean).join(" · ");
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "text";
      toggle.textContent = person.sign_in ? "Close sign-in" : "Open sign-in";
      toggle.addEventListener("click", async () => {
        const changed = await call("/api/auth/desk/people/sign-in", { email: person.email, enabled: !person.sign_in });
        if (!changed.ok) {
          line.textContent = changed.data.error || "Could not change sign-in.";
          return;
        }
        loadPeople();
        paintDesk({ email: document.getElementById("who").textContent.split(" · ")[0], role: "admin" });
      });
      item.append(line, toggle);
      list.appendChild(item);
    });
  }

  async function loadSignups() {
    const result = await call("/api/auth/desk/signups");
    const signups = result.ok ? result.data.signups || [] : [];
    const list = fillList("[data-signups]", signups, result.ok ? "No signup in progress." : (result.data.error || "Could not load verification."));
    signups.forEach((row) => {
      const item = document.createElement("li");
      const checks = [
        row.email_ok ? "email" : "",
        row.mobile_ok ? "mobile" : "",
        row.aadhaar_ok ? "aadhaar" : "",
        row.pan_ok ? "pan" : "",
      ].filter(Boolean);
      item.textContent = [
        row.email,
        row.role,
        row.mobile_last4 ? "····" + row.mobile_last4 : "",
        checks.length ? checks.join(", ") : "checks pending",
        row.open ? "open" : "expired",
      ].filter(Boolean).join(" · ");
      list.appendChild(item);
    });
  }

  async function loadProcesses() {
    const result = await call("/api/auth/desk/processes");
    const processes = result.ok ? result.data.processes || [] : [];
    const list = fillList("[data-processes]", processes, result.data.error || "Could not read the processes.");
    processes.forEach((row) => {
      const item = document.createElement("li");
      item.textContent = row.name + " · " + row.port + " · " + (row.up ? "up" : "down");
      list.appendChild(item);
    });
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
    if (!created.ok) return error(form, created.data.error || "Could not create the admin.");
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

  function scanUri(otpauth) {
    const match = typeof otpauth === "string" ? otpauth.match(/^otpauth:\/\/totp\/([^?]+)\?(.*)$/) : null;
    if (!match) return otpauth || "";
    return "otpauth://totp/" + encodeURIComponent(match[1]) + "?" + match[2];
  }

  document.getElementById("start-enroll").addEventListener("click", async () => {
    const result = await call("/api/auth/mfa/setup", {});
    if (!result.ok) return error(document.getElementById("enroll-confirm"), result.data.error || "Could not start setup.");
    const secret = document.querySelector("[data-secret]");
    const codes = document.querySelector("[data-codes]");
    secret.hidden = false;
    secret.textContent = result.data.secret;
    document.querySelector("[data-secret-label]").hidden = false;
    const qr = document.querySelector("[data-qr]");
    const drawn = window.drawAuthenticatorQr && drawAuthenticatorQr(document.querySelector("[data-qr-canvas]"), scanUri(result.data.otpauth));
    qr.hidden = !drawn;
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

  document.querySelector(".rooms").addEventListener("click", (event) => {
    const button = event.target.closest("[data-room]");
    if (button) room(button.dataset.room);
  });

  document.getElementById("logout").addEventListener("click", async () => {
    await call("/api/auth/logout", {});
    show("login");
  });

  const addForm = document.getElementById("add-account");
  let addStep = "details";
  let addSignup = "";

  function field(name) {
    return addForm.elements.namedItem(name);
  }

  function addError(message) {
    const node = addForm.querySelector("[data-add-error]");
    node.hidden = !message;
    node.textContent = message || "";
  }

  function showAddStep(step) {
    addStep = step;
    addForm.querySelectorAll("[data-add]").forEach((node) => {
      node.hidden = node.dataset.add !== step;
    });
    const labels = {
      details: field("role").value === "admin" ? "Add admin" : "Send codes",
      codes: "Verify email and mobile",
      aadhaar: "Open DigiLocker",
      "aadhaar-done": "I finished DigiLocker",
      pan: "Check PAN and create account",
    };
    addForm.querySelector("[data-add-submit]").textContent = labels[step];
    addForm.querySelector("[data-add-mobile]").hidden = field("role").value === "admin" && step === "details";
  }

  field("role").addEventListener("change", () => {
    addSignup = "";
    showAddStep("details");
  });

  addForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    addError("");
    const role = field("role").value;
    if (addStep === "details" && role === "admin") {
      const created = await call("/api/auth/desk/accounts", {
        email: field("email").value,
        password: field("password").value,
        role: "admin",
      });
      if (!created.ok) return addError(created.data.error || "Could not add the admin.");
      addForm.reset();
      field("role").value = "customer";
      showAddStep("details");
      return enter({ email: document.getElementById("who").textContent.split(" · ")[0], role: "admin" });
    }
    if (addStep === "details") {
      const started = await call("/api/auth/signup/start", {
        email: field("email").value,
        mobile: field("mobile").value,
        password: field("password").value,
        role,
      });
      if (!started.ok) return addError(started.data.error || "Could not send the codes.");
      addSignup = started.data.signup_id;
      showAddStep("codes");
      return;
    }
    if (addStep === "codes") {
      const contact = await call("/api/auth/signup/contact", {
        signup_id: addSignup,
        email_code: field("email_code").value,
        sms_code: field("sms_code").value,
      });
      if (!contact.ok) return addError(contact.data.error || "Verification did not succeed.");
      if (contact.data.account_ready) {
        addForm.reset();
        showAddStep("details");
        return enter({ email: document.getElementById("who").textContent.split(" · ")[0], role: "admin" });
      }
      showAddStep("aadhaar");
      return;
    }
    if (addStep === "aadhaar") {
      const sent = await call("/api/auth/signup/aadhaar", { signup_id: addSignup });
      if (!sent.ok || !sent.data.url) return addError(sent.data.error || "Verification did not succeed.");
      window.open(sent.data.url, "_blank", "noopener");
      showAddStep("aadhaar-done");
      return;
    }
    if (addStep === "aadhaar-done") {
      const confirmed = await call("/api/auth/signup/aadhaar/confirm", { signup_id: addSignup });
      if (!confirmed.ok) return addError(confirmed.data.error || "Verification did not succeed.");
      showAddStep("pan");
      return;
    }
    const created = await call("/api/auth/signup/pan", {
      signup_id: addSignup,
      pan: field("pan").value,
      name: field("pan_name").value,
    });
    if (!created.ok || !created.data.account_ready) return addError(created.data.error || "Verification did not succeed.");
    addForm.reset();
    showAddStep("details");
    return enter({ email: document.getElementById("who").textContent.split(" · ")[0], role: "admin" });
  });

  Promise.all([call("/api/auth/me"), call("/api/auth/setup")]).then(([me, setup]) => {
    const create = document.querySelector("[data-show='register']");
    if (setup.data.signup_open) create.hidden = false;
    if (me.ok && me.data.role === ROLE) enter(me.data);
    else if (me.status === 403 && me.data.mfa_setup_required && me.data.role === ROLE) show("enroll");
    else show("login");
  });
})();
