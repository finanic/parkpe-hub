/* Backend admin console.

   Served by auth.server._console from this same process.
   Calls the routes in auth.contract.Paths with role "admin".
   Payswap and ParkPe do not load this file.
   Confirm and password dialogs live in apps/backend/auth/console/index.html.
*/
(function () {
  const ROLE = "admin";
  const MORE_ICON = '<svg class="icon dots" viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.25"></circle><circle cx="12" cy="12" r="1.25"></circle><circle cx="19" cy="12" r="1.25"></circle></svg>';

  let pickedAddRole = "customer";

  function paintAddRolePick() {
    const form = document.getElementById("add-account");
    if (!form) return;
    form.querySelectorAll("[data-add-role]").forEach((button) => {
      const on = button.dataset.addRole === pickedAddRole;
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function addAccountRole() {
    return pickedAddRole;
  }

  function setAddAccountRole(role) {
    if (role !== "customer" && role !== "retailer" && role !== "admin") role = "customer";
    if (role === "admin" && !deskSuper) role = "customer";
    pickedAddRole = role;
    paintAddRolePick();
  }

  function deskDeviceId() {
    const key = "hub-device-id";
    try {
      let id = localStorage.getItem(key);
      if (id && id.length >= 16) return id;
      id =
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `hub-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
      localStorage.setItem(key, id);
      return id;
    } catch (_err) {
      return `hub-ephemeral-${Date.now().toString(36)}`;
    }
  }

  function moneyKey() {
    if (globalThis.crypto && typeof crypto.randomUUID === "function") return crypto.randomUUID();
    return `adj-${Date.now().toString(36)}`;
  }

  async function call(path, payload, extraHeaders) {
    const headers = { "X-Auth-Request": "1" };
    if (extraHeaders) Object.assign(headers, extraHeaders);
    const init = { method: "GET", credentials: "same-origin", headers };
    if (payload !== undefined) {
      init.method = "POST";
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify({ ...payload, device_id: deskDeviceId() });
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
    people: "Account Hub",
    parkpe: "ParkPe",
    payswap: "PaySwap",
    "fund-requests": "Fund Requests",
    verification: "Account Hub",
    services: "API & Services",
    billing: "Billing & Settlements",
    reports: "Transaction Reports",
    processes: "System Health",
    logs: "Logs",
  };
  const ROOM_CRUMB = {
    overview: "Overview",
    people: "Account Hub",
    parkpe: "ParkPe",
    payswap: "PaySwap",
    "fund-requests": "Fund Requests",
    verification: "Account Hub / Verification",
    services: "API & Services",
    billing: "Billing & Settlements",
    reports: "Transaction Reports",
    processes: "System Health",
    logs: "Logs",
  };

  function show(name) {
    document.querySelectorAll("[data-view]").forEach((node) => {
      node.hidden = node.dataset.view !== name;
    });
    document.getElementById("gate").hidden = name === "home";
  }

  const DESK_ROUTE_KEY = "admin-desk-route";
  const PAYSWAP_VIEWS = new Set(["hub", "policy", "bbps", "retailers", "activity", "bulk", "commission"]);
  const ECON_VIEWS = new Set(["hub", "commission", "tds", "gst"]);
  const PAYSWAP_CRUMB = {
    policy: "Retailer policy",
    bbps: "BBPS",
    retailers: "Retailer services",
    activity: "Live activity",
    bulk: "Bulk bills",
    commission: "Economics",
  };
  const ECON_CRUMB = { commission: "Commission", tds: "TDS", gst: "GST" };

  function readDeskRoute() {
    let raw = (location.hash || "").replace(/^#/, "");
    try {
      raw = decodeURIComponent(raw);
    } catch (_err) {
      /* keep raw */
    }
    if (!raw) {
      try {
        raw = sessionStorage.getItem(DESK_ROUTE_KEY) || "";
      } catch (_err) {
        raw = "";
      }
    }
    const parts = raw.split("/").map((p) => p.trim()).filter(Boolean);
    const roomName = ROOM_TITLE[parts[0]] ? parts[0] : "overview";
    const payswap = roomName === "payswap" && PAYSWAP_VIEWS.has(parts[1]) ? parts[1] : "hub";
    const econ = payswap === "commission" && ECON_VIEWS.has(parts[2]) ? parts[2] : "hub";
    return { room: roomName, payswap, econ };
  }

  function writeDeskRoute() {
    let path = currentRoom || "overview";
    if (currentRoom === "payswap" && payswapView && payswapView !== "hub") {
      path += "/" + payswapView;
      if (payswapView === "commission" && econView && econView !== "hub") {
        path += "/" + econView;
      }
    }
    try {
      sessionStorage.setItem(DESK_ROUTE_KEY, path);
    } catch (_err) {
      /* private mode */
    }
    if (location.hash !== "#" + path) history.replaceState(null, "", "#" + path);
  }

  function deskCrumb(name) {
    const bits = ["Workspace", ROOM_CRUMB[name] || ROOM_TITLE[name] || "Dashboard"];
    if (name === "payswap" && payswapView && payswapView !== "hub") {
      bits.push(PAYSWAP_CRUMB[payswapView] || payswapView);
      if (payswapView === "commission" && econView && econView !== "hub") {
        bits.push(ECON_CRUMB[econView] || econView);
      }
    }
    return bits.join(" / ");
  }

  function room(name, opts) {
    const restore = Boolean(opts && opts.restore);
    document.querySelectorAll("[data-room]").forEach((node) => {
      const on = node.dataset.room === name || (node.dataset.room === "people" && name === "verification");
      node.classList.toggle("is-on", on);
      if (on) node.setAttribute("aria-current", "page");
      else node.removeAttribute("aria-current");
    });
    document.querySelectorAll("[data-panel]").forEach((node) => {
      node.hidden = node.dataset.panel !== name;
    });
    const title = ROOM_TITLE[name] || "Dashboard";
    document.getElementById("page-title").textContent = title;
    document.title = title + " · Backend";
    currentRoom = name;
    setNav(false);
    if (name === "overview") loadOverview();
    if (name === "people") loadPeople();
    if (name === "verification") loadVerifications();
    if (name === "services") loadServices();
    if (name === "processes") loadProcesses();
    if (name === "parkpe") loadParkpe();
    if (name === "payswap") {
      if (!restore) {
        payswapView = "hub";
        econView = "hub";
      }
      loadPayswap();
      if (restore && payswapView === "commission" && econView && econView !== "hub") {
        openEconView(econView);
      } else if (payswapView === "commission") {
        showEconView(econView || "hub");
      }
    }
    if (name === "fund-requests") loadFundRequests();
    if (name === "reports") loadReports();
    if (name === "logs") loadLogs();
    document.querySelectorAll("[data-account-view]").forEach((button) => {
      const on = button.dataset.accountView === name;
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-current", on ? "page" : "false");
    });
    document.getElementById("crumb").textContent = deskCrumb(name);
    writeDeskRoute();
  }

  function fillList(selector, rows, empty) {
    const list = document.querySelector(selector);
    list.replaceChildren();
    if (!rows.length) {
      const item = document.createElement("li");
      item.className = "is-empty";
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

  function initials(email) {
    const local = String(email || "").split("@")[0];
    const bits = local.split(/[^A-Za-z0-9]+/).filter(Boolean);
    if (!bits.length) return "—";
    const second = bits[1] ? bits[1].slice(0, 1) : bits[0].slice(1, 2);
    return (bits[0].slice(0, 1) + second).toUpperCase();
  }

  function currentEmail() {
    return document.getElementById("who").dataset.email || "";
  }

  function roleLabel(role) {
    if (role === "customer") return "Customer";
    if (role === "retailer") return "Retailer";
    if (role === "admin") return "Admin";
    return role;
  }

  function badge(text, kind) {
    const node = document.createElement("span");
    node.className = kind ? "pill " + kind : "pill";
    node.textContent = text;
    return node;
  }

  async function paintDesk(user) {
    const desk = await call("/api/auth/desk");
    const data = desk.ok ? desk.data : {};
    const email = data.email || (user && user.email) || "";
    const who = document.getElementById("who");
    who.dataset.email = email;
    who.textContent = email;
    const counts = data.counts || {};
    if (desk.ok) {
      ["customer", "retailer"].forEach((key) => {
        const node = document.querySelector('[data-count="' + key + '"]');
        if (node) node.textContent = Number(counts[key] || 0).toLocaleString("en-IN");
      });
    }
    applySuper(!!data.super);
    const hour = new Date().getHours();
    const hello = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
    document.getElementById("hello").textContent = hello + ", " + (deskSuper ? "Super Admin" : "Admin") + " 👋";
    document.getElementById("top-avatar").title = deskSuper ? "Super Admin" : "Admin";
    const signups = await call("/api/auth/desk/signups");
    document.querySelectorAll("[data-verify-count]").forEach((node) => {
      node.textContent = String(signups.ok ? (signups.data.pending || signups.data.signups || []).length : 0);
    });
    document.getElementById("today").textContent = new Date().toLocaleDateString("en-IN", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
    if (desk.ok) paintEvents(data.events || []);
    await loadOverview();
  }

  function inr(val) {
    const n = Number(val || 0);
    return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadOverview() {
    const [ovRes, procRes, svcRes] = await Promise.all([
      call("/api/auth/desk/overview"),
      call("/api/auth/desk/processes"),
      call("/api/auth/desk/services"),
    ]);
    if (ovRes.ok && ovRes.data) {
      const d = ovRes.data;
      const setText = (sel, txt) => {
        const el = document.querySelector(sel);
        if (el) el.textContent = txt;
      };
      setText("[data-overview-bbps-today]", inr(d.today_bbps_volume));
      setText("[data-overview-bbps-count]", `${d.today_bbps_count || 0} txns (${d.today_bbps_pending || 0} pending)`);
      setText("[data-overview-wallet-float]", inr(d.total_wallet_available));
      setText("[data-overview-topups-pending]", `${d.pending_topup_count || 0} pending top-ups`);
      setText("[data-fund-pending-count]", String(d.pending_topup_count || 0));
      const series = Array.isArray(d.daily_series) ? d.daily_series : [];
      const sum7 = series.reduce((a, x) => a + Number(x.amount || 0), 0);
      setText("[data-overview-7d-total]", inr(sum7));
      const barsEl = document.querySelector("[data-overview-series]");
      if (barsEl) {
        const maxVal = Math.max(1, ...series.map((x) => Number(x.amount || 0)));
        barsEl.replaceChildren();
        series.forEach((item) => {
          const col = document.createElement("div");
          col.className = "series-col";
          const val = document.createElement("span");
          val.textContent = Number(item.amount || 0) > 0 ? "₹" + Math.round(Number(item.amount)) : "0";
          const bar = document.createElement("div");
          bar.className = "series-bar";
          bar.style.height = Math.max(4, Math.round((Number(item.amount || 0) / maxVal) * 86)) + "px";
          const lbl = document.createElement("small");
          lbl.textContent = item.date;
          col.append(val, bar, lbl);
          barsEl.appendChild(col);
        });
      }
    }
    const healthBox = document.querySelector("[data-overview-health]");
    const badge = document.querySelector("[data-overview-health-badge]");
    if (healthBox) {
      healthBox.replaceChildren();
      const items = [];
      if (procRes.ok && Array.isArray(procRes.data.processes)) {
        procRes.data.processes.forEach((p) => {
          items.push({
            icon: "◈",
            title: `${p.name} (:${p.port})`,
            sub: p.url || "Local service",
            ok: Boolean(p.up),
            label: p.up ? "Up" : "Down",
          });
        });
      }
      if (svcRes.ok && Array.isArray(svcRes.data.services)) {
        svcRes.data.services
          .filter((s) => ["bbps", "pg", "payu", "cashfree"].includes(s.id))
          .forEach((s) => {
            items.push({
              icon: "⌁",
              title: s.name,
              sub: s.status_label,
              ok: s.state === "ready",
              label: s.status_label,
            });
          });
      }
      const allUp = items.length > 0 && items.every((i) => i.ok);
      if (badge) {
        badge.textContent = allUp ? "ALL SYSTEMS READY" : "CHECK STATUS";
        badge.className = allUp ? "status" : "status warn";
      }
      items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "health-item";
        row.innerHTML = `<div class="health-icon" aria-hidden="true">${escHtml(item.icon)}</div><div class="health-copy"><b>${escHtml(item.title)}</b><small>${escHtml(item.sub)}</small></div><span class="status ${item.ok ? "" : "warn"}">${escHtml(item.label)}</span>`;
        healthBox.appendChild(row);
      });
    }
  }

  const FAILED_EVENTS = new Set([
    "login_failed",
    "mfa_failed",
    "sign_in_closed",
    "register_operator_closed",
    "signup_rejected",
    "signup_delivery_failed",
    "refresh_reuse",
    "server_error",
  ]);

  function eventLabel(name) {
    const text = String(name || "event").replaceAll("_", " ");
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function paintEvents(events) {
    const list = document.querySelector("[data-events]");
    list.replaceChildren();
    if (!events.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 4;
      cell.className = "is-empty";
      cell.textContent = "No auth events yet.";
      row.appendChild(cell);
      list.appendChild(row);
      return;
    }
    events.forEach((event) => {
      const failed = FAILED_EVENTS.has(event.event);
      const row = document.createElement("tr");
      const activity = document.createElement("td");
      const label = document.createElement("div");
      label.className = "event";
      const dot = document.createElement("span");
      dot.className = "event-dot" + (failed ? " orange" : event.event === "login" ? " green" : "");
      label.append(dot, document.createTextNode(eventLabel(event.event)));
      activity.appendChild(label);
      const user = document.createElement("td");
      user.textContent = event.email || "—";
      const time = document.createElement("td");
      time.textContent = new Date(event.at * 1000).toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      });
      const status = document.createElement("td");
      const pill = document.createElement("span");
      pill.className = failed ? "pill failed" : "pill success";
      pill.textContent = failed ? "Failed" : "Success";
      status.appendChild(pill);
      row.append(activity, user, time, status);
      list.appendChild(row);
    });
  }

  async function enter(user) {
    await paintDesk(user);
    show("home");
    const saved = readDeskRoute();
    payswapView = saved.payswap;
    econView = saved.econ;
    room(saved.room, { restore: true });
  }

  let peopleRows = [];
  let currentRoom = "overview";
  let deskSuper = false;
  let userFilter = "all";
  let confirmResolve = null;
  let passwordResolve = null;
  let lastFocus = null;

  function applySuper(isSuper) {
    deskSuper = isSuper;
    const adminPick = document.querySelector("[data-role-admin]");
    if (adminPick) adminPick.hidden = !deskSuper;
    paintAddRolePick();
    if (!deskSuper && addAccountRole() === "admin") {
      setAddAccountRole("customer");
      showAddStep("details");
    }
    const rank = deskSuper ? "Super Admin" : "Admin";
    document.getElementById("desk-rank").textContent = rank;
    const mark = deskSuper ? "SA" : "AD";
    document.getElementById("desk-avatar").textContent = mark;
    document.getElementById("top-avatar").textContent = mark;
  }

  function captureDeskLocation(latInput, lngInput, sourceInput, onError) {
    if (!latInput || !lngInput || !navigator.geolocation) {
      if (sourceInput) sourceInput.value = "";
      onError("Allow location for this desk. Typed coordinates are not accepted.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        latInput.value = Number(pos.coords.latitude).toFixed(6);
        lngInput.value = Number(pos.coords.longitude).toFixed(6);
        if (sourceInput) sourceInput.value = "desk";
        onError("");
      },
      () => {
        if (sourceInput) sourceInput.value = "";
        onError("Allow location for this desk. Typed coordinates are not accepted.");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  }

  function actionButton(label, onClick, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className || "text";
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
  }

  function menuItem(label, onClick, danger) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = danger ? "menu-item danger" : "menu-item";
    button.setAttribute("role", "menuitem");
    button.textContent = label;
    button.addEventListener("click", () => {
      closeMenus();
      onClick();
    });
    return button;
  }

  function rememberFocus() {
    lastFocus = document.activeElement;
  }

  function restoreFocus() {
    if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
    lastFocus = null;
  }

  function askConfirm(options) {
    const modal = document.getElementById("confirm");
    document.getElementById("confirm-title").textContent = options.title;
    document.querySelector("[data-confirm-body]").textContent = options.body;
    const ok = document.querySelector("[data-confirm-ok]");
    ok.textContent = options.confirm;
    ok.className = options.danger ? "danger" : "primary";
    rememberFocus();
    modal.hidden = false;
    (options.danger ? modal.querySelector("[data-confirm-cancel]") : ok).focus();
    return new Promise((resolve) => {
      confirmResolve = resolve;
    });
  }

  function settleConfirm(value) {
    const modal = document.getElementById("confirm");
    if (modal.hidden && !confirmResolve) return;
    modal.hidden = true;
    const resolve = confirmResolve;
    confirmResolve = null;
    if (resolve) resolve(!!value);
    restoreFocus();
  }

  function passwordError(message) {
    const node = document.querySelector("[data-password-error]");
    node.hidden = !message;
    node.textContent = message || "";
  }

  function deskTarget(person) {
    return { user_id: person.id, email: person.email };
  }

  function roleAccountId(person, role) {
    if (role !== "customer" && role !== "retailer") return "";
    const prefix = role === "retailer" ? "R00" : "CU00";
    const source = String(person.user_id || person.id || "").replace(/[^A-Za-z0-9]/g, "").toUpperCase();
    return prefix + (source.slice(-8) || "PENDING");
  }

  function accountIdsFor(person) {
    return (person.roles || [])
      .filter((role) => role === "customer" || role === "retailer")
      .map((role) => roleAccountId(person, role));
  }

  function accountIdForEmail(email, role) {
    const person = peopleRows.find((row) => String(row.email || "").toLowerCase() === String(email || "").toLowerCase());
    return person && (person.roles || []).includes(role) ? roleAccountId(person, role) : "";
  }

  function askPassword(person) {
    const modal = document.getElementById("password-modal");
    modal.dataset.userId = person.id || "";
    document.querySelector("[data-password-for]").textContent = person.email;
    modal.password.value = "";
    passwordError("");
    rememberFocus();
    modal.hidden = false;
    modal.password.focus();
    return new Promise((resolve) => {
      passwordResolve = resolve;
    });
  }

  function settlePassword(value) {
    const modal = document.getElementById("password-modal");
    if (modal.hidden && !passwordResolve) return;
    modal.hidden = true;
    modal.password.value = "";
    const resolve = passwordResolve;
    passwordResolve = null;
    if (resolve) resolve(!!value);
    restoreFocus();
  }

  function paintPeople() {
    const query = (document.getElementById("people-filter").value || "").trim().toLowerCase();
    const total = document.querySelector("[data-people-total]");
    if (total) total.textContent = peopleRows.length + (peopleRows.length === 1 ? " account" : " accounts");
    document.querySelectorAll("[data-user-filter]").forEach((button) => {
      const on = button.dataset.userFilter === userFilter;
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
      const count = button.querySelector("[data-filter-count]");
      if (!count) return;
      const key = button.dataset.userFilter;
      const total = key === "all"
        ? peopleRows.length
        : peopleRows.filter((person) => (person.roles || []).includes(key)).length;
      count.textContent = String(total);
    });
    const people = peopleRows.filter((person) => {
      const roles = person.roles || [];
      if (userFilter !== "all" && !roles.includes(userFilter)) return false;
      if (!query) return true;
      const haystack = [
        person.email,
        roles.join(" "),
        accountIdsFor(person).join(" "),
        person.super ? "super admin" : "",
        person.authenticator ? "2fa on authenticator" : "2fa off authenticator",
        person.sign_in ? "sign-in open" : "sign-in closed",
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    });
    const list = fillList("[data-people]", people, peopleRows.length ? "No matching account." : "No accounts yet.");
    people.forEach((person) => {
      const item = document.createElement("li");
      const personBox = document.createElement("div");
      personBox.className = "person";
      const idRow = document.createElement("div");
      idRow.className = "person-id";
      const avatar = document.createElement("span");
      avatar.className = "avatar";
      avatar.textContent = initials(person.email);
      const email = document.createElement("strong");
      email.textContent = person.email;
      email.title = person.email;
      idRow.append(avatar, email);
      const badges = document.createElement("div");
      badges.className = "badges";
      (person.roles || []).forEach((role) => badges.append(badge(roleLabel(role), "")));
      accountIdsFor(person).forEach((id) => badges.append(badge(id, "account-id")));
      if (person.super) badges.append(badge("Super admin", "super"));
      badges.append(badge(person.authenticator ? "2FA On" : "2FA Off", person.authenticator ? "ok" : "off"));
      badges.append(badge(person.sign_in ? "Sign-in Open" : "Sign-in Closed", person.sign_in ? "ok" : "off"));
      const note = document.createElement("p");
      note.className = "row-note";
      note.hidden = true;
      personBox.append(idRow, badges, note);
      function setNote(message, isError) {
        note.hidden = !message;
        note.textContent = message || "";
        note.classList.toggle("is-error", !!isError);
      }

      const actions = document.createElement("div");
      actions.className = "row-actions";
      const adminTarget = (person.roles || []).includes("admin");
      const canChangeAdmin = deskSuper || !adminTarget;
      actions.append(actionButton("Open file", () => openFile(person), "primary btn-sm"));
      actions.append(actionButton("Sessions", async () => {
        setNote("Loading sessions…", false);
        const result = await call(
          "/api/auth/desk/people/sessions?user_id=" + encodeURIComponent(person.id)
        );
        if (!result.ok) {
          setNote(result.data.error || "Could not load sessions.", true);
          return;
        }
        const open = result.data.sessions || [];
        setNote(open.length
          ? open.map((row) => [row.role, row.scope].filter(Boolean).join(" ")).join(", ")
          : "No open session.", false);
      }, "quiet"));

      const more = document.createElement("div");
      more.className = "more";
      const moreBtn = document.createElement("button");
      moreBtn.type = "button";
      moreBtn.className = "icon-btn";
      moreBtn.setAttribute("data-more", "");
      moreBtn.setAttribute("aria-haspopup", "menu");
      moreBtn.setAttribute("aria-expanded", "false");
      moreBtn.setAttribute("aria-label", "More actions for " + person.email);
      moreBtn.innerHTML = MORE_ICON;
      const menu = document.createElement("div");
      menu.className = "menu";
      menu.hidden = true;
      menu.setAttribute("role", "menu");
      if (canChangeAdmin || person.email === currentEmail()) {
        menu.append(
          menuItem("New password", async () => {
            const updated = await askPassword(person);
            if (updated) setNote("Password updated.", false);
          }),
          menuItem("Reset authenticator", async () => {
            const ok = await askConfirm({
              title: "Reset authenticator",
              body: "Reset the authenticator for " + person.email + "?",
              confirm: "Reset authenticator",
              danger: true,
            });
            if (!ok) return;
            const result = await call("/api/auth/desk/people/authenticator", deskTarget(person));
            if (result.ok && result.data.self) {
              show("login");
              return;
            }
            if (!result.ok) {
              setNote(result.data.error || "Could not reset the authenticator.", true);
              return;
            }
            loadPeople();
          })
        );
      }
      if (canChangeAdmin) {
        menu.append(menuItem(person.sign_in ? "Close sign-in" : "Open sign-in", async () => {
          const closing = !!person.sign_in;
          const ok = await askConfirm({
            title: closing ? "Close sign-in" : "Open sign-in",
            body: (closing ? "Close sign-in for " : "Open sign-in for ") + person.email + "?",
            confirm: closing ? "Close sign-in" : "Open sign-in",
            danger: closing,
          });
          if (!ok) return;
          const changed = await call(
            "/api/auth/desk/people/sign-in",
            Object.assign({ enabled: !person.sign_in }, deskTarget(person))
          );
          if (!changed.ok) {
            setNote(changed.data.error || "Could not change sign-in.", true);
            return;
          }
          loadPeople();
          paintDesk({ email: currentEmail(), role: ROLE });
        }));
      }
      const removes = [];
      (person.roles || []).forEach((role) => {
        if (role === "admin" && !deskSuper) return;
        removes.push(menuItem("Remove " + role, async () => {
          const ok = await askConfirm({
            title: "Remove " + role,
            body: "Remove " + role + " from " + person.email + "?",
            confirm: "Remove " + role,
            danger: true,
          });
          if (!ok) return;
          const result = await call("/api/auth/desk/people/role", Object.assign({ role }, deskTarget(person)));
          if (!result.ok) {
            setNote(result.data.error || "Could not remove the role.", true);
            return;
          }
          loadPeople();
        }, true));
      });
      if (removes.length) {
        menu.append(document.createElement("hr"));
        removes.forEach((button) => menu.append(button));
      }
      moreBtn.addEventListener("click", () => {
        const willOpen = menu.hidden;
        closeMenus();
        if (!willOpen) return;
        menu.hidden = false;
        moreBtn.setAttribute("aria-expanded", "true");
        const rect = menu.getBoundingClientRect();
        if (rect.bottom > window.innerHeight - 12) menu.classList.add("is-up");
      });
      more.append(moreBtn, menu);
      actions.append(more);
      item.append(personBox, actions);
      list.appendChild(item);
    });
  }

  function rolesForEmail(email) {
    const clean = String(email || "").trim().toLowerCase();
    const roles = new Set();
    peopleRows.forEach((person) => {
      if (String(person.email || "").trim().toLowerCase() !== clean) return;
      (person.roles || []).forEach((role) => roles.add(role));
    });
    return roles;
  }

  function preferProductRoleForSignup(email, role) {
    if (role === "admin") return role;
    const existing = rolesForEmail(email);
    if (existing.has("customer") && !existing.has("retailer") && role === "customer") {
      setAddAccountRole("retailer");
      return "retailer";
    }
    if (existing.has("retailer") && !existing.has("customer") && role === "retailer") {
      setAddAccountRole("customer");
      return "customer";
    }
    return role;
  }

  async function loadPeople() {
    const result = await call("/api/auth/desk/people");
    peopleRows = result.ok ? result.data.people || [] : [];
    const dl = document.getElementById("retailer-email-list");
    if (dl) {
      dl.replaceChildren();
      peopleRows
        .filter((p) => (p.roles || [p.role]).includes("retailer"))
        .forEach((p) => {
          const opt = document.createElement("option");
          opt.value = p.email;
          dl.appendChild(opt);
        });
    }
    if (!result.ok) {
      fillList("[data-people]", [], result.data.error || "Could not load people.");
      return;
    }
    paintPeople();
  }

  function fillPlain(selector, rows, empty, label) {
    const list = fillList(selector, rows, empty);
    rows.forEach((row) => {
      const item = document.createElement("li");
      item.textContent = label(row);
      list.appendChild(item);
    });
  }

  async function openFile(person) {
    const panel = document.querySelector("[data-user-file]");
    panel.hidden = false;
    panel.scrollIntoView({ block: "nearest" });
    const result = await call("/api/auth/desk/users/file?user_id=" + encodeURIComponent(person.id));
    const summary = document.querySelector("[data-user-summary]");
    if (!result.ok) {
      summary.textContent = result.data.error || "Could not open the file.";
      return;
    }
    const file = result.data;
    const focusRole = person.roles && person.roles.length === 1 ? person.roles[0] : null;
    const profileRows = focusRole
      ? (file.profiles || []).filter((row) => row.role === focusRole)
      : (file.profiles || []);
    const flags = profileRows.map((row) => {
      const checks = [];
      if (row.email_ok) checks.push("email");
      if (row.mobile_ok) checks.push("mobile");
      if (row.aadhaar_ok) checks.push("aadhaar");
      if (row.pan_ok) checks.push("pan");
      const tail = row.mobile_last4 ? "····" + row.mobile_last4 : "";
      return [row.role, tail, checks.join(", ") || "checks pending"].filter(Boolean).join(" ");
    });
    summary.textContent = [
      file.email,
      accountIdsFor({ id: person.id, roles: focusRole ? [focusRole] : file.roles || [] }).join(" / "),
      focusRole ? roleLabel(focusRole) : (file.roles || []).join(", "),
      file.super ? "super admin" : "",
      file.authenticator ? "authenticator on" : "authenticator off",
      file.sign_in ? "sign-in open" : "sign-in closed",
      flags.join(" · "),
    ].filter(Boolean).join(" · ");
    const idHost = document.querySelector("[data-user-account-ids]");
    const accountIds = accountIdsFor({ id: person.id, roles: focusRole ? [focusRole] : file.roles || [] });
    if (idHost) {
      idHost.replaceChildren();
      accountIds.forEach((id) => idHost.append(badge(id, "account-id")));
      idHost.hidden = !accountIds.length;
    }
    const verifyBox = document.querySelector("[data-user-verify]");
    const verifyHost = document.querySelector("[data-user-verify-checks]");
    const showChecks = focusRole && (focusRole === "customer" || focusRole === "retailer");
    if (verifyBox) verifyBox.hidden = !showChecks;
    if (showChecks && verifyHost) {
      paintVerifyProfileChecks({ role: focusRole }, file.profiles, "[data-user-verify-checks]");
    }
    const kycBox = document.querySelector("[data-user-kyc]");
    const kycHost = document.querySelector("[data-user-kyc-fields]");
    const kycProfile = profileRows[0];
  const kycHasData =
      kycProfile &&
      (kycProfile.mobile || kycProfile.pan || kycProfile.pan_name || kycProfile.digilocker_verification_id);
    if (kycBox) kycBox.hidden = !showChecks || !kycHasData;
    if (kycHost && kycHasData) {
      kycHost.replaceChildren();
      const rows = [
        ["Mobile", kycProfile.mobile || "—"],
        ["PAN", kycProfile.pan || kycProfile.pan_mask || "—"],
        ["Name on PAN", kycProfile.pan_name || kycProfile.pan_name_hint || "—"],
        ["PAN registry name", kycProfile.pan_registered_name || "—"],
        ["DigiLocker session", kycProfile.digilocker_verification_id || kycProfile.digilocker_ref || "—"],
        ["GSTIN", kycProfile.gstin || "—"],
        ["Udyam", kycProfile.udyam || "—"],
        ["Business name", kycProfile.business_legal_name || "—"],
        ["Outlet check", kycProfile.business_status || "—"],
        ["Desk-captured location", kycProfile.location_source === "desk" && kycProfile.shop_lat && kycProfile.shop_lng ? kycProfile.shop_lat + ", " + kycProfile.shop_lng : "—"],
        ["Desk IP", kycProfile.verification_ip || "—"],
        ["Recorded", kycProfile.recorded_at ? new Date(kycProfile.recorded_at * 1000).toLocaleString() : "—"],
      ];
      rows.forEach(([label, value]) => {
        const dt = document.createElement("dt");
        dt.textContent = label;
        const dd = document.createElement("dd");
        dd.textContent = value;
        kycHost.append(dt, dd);
      });
    }
    fillPlain(
      "[data-user-sessions]",
      file.sessions || [],
      "No open session.",
      (row) => [row.role, row.scope].filter(Boolean).join(" · ")
    );
    const customer = focusRole ? focusRole === "customer" : (file.roles || []).includes("customer");
    const retailer = focusRole ? focusRole === "retailer" : (file.roles || []).includes("retailer");
    document.querySelector("[data-user-customer]").hidden = !customer;
    document.querySelector("[data-user-retailer]").hidden = !retailer;
    if (customer) {
      const parked = await call("/api/auth/desk/parkpe?email=" + encodeURIComponent(file.email));
      const stored = parked.ok ? parked.data.sessions || [] : [];
      fillPlain(
        "[data-user-parkpe]",
        stored,
        parked.ok ? "No stored ParkPe session yet." : (parked.data.error || "Could not load ParkPe."),
        (row) => [row.reference, row.site_code, row.bay, row.vehicle, row.state].filter(Boolean).join(" · ")
      );
    }
    if (retailer) {
      const [ordered, walletRes] = await Promise.all([
        call("/api/auth/desk/payswap?email=" + encodeURIComponent(file.email)),
        call("/api/auth/desk/wallets?email=" + encodeURIComponent(file.email)),
      ]);
      const stored = ordered.ok ? ordered.data.orders || [] : [];
      fillPlain(
        "[data-user-orders]",
        stored,
        ordered.ok ? "No stored PaySwap order yet." : (ordered.data.error || "Could not load PaySwap."),
        (row) => [row.reference, row.brand, row.amount, row.state].filter(Boolean).join(" · ")
      );
      renderRetailerControls(file.email, walletRes.ok ? walletRes.data : null);
    }
  }

  function renderRetailerControls(email, payload) {
    const host = document.querySelector("[data-user-retailer-controls]");
    if (!host) return;
    if (!payload) {
      host.innerHTML = `<p class="note">Could not load wallet &amp; permissions.</p>`;
      return;
    }
    const w = payload.wallet || {};
    const ent = payload.entitlements || {};
    const catalog = ent.catalog || [];
    const svcOverrides = ent.service_overrides || {};
    const payOverrides = ent.payment_overrides || {};
    const modes = ent.payment_modes || {};
    const frozen = w.status === "frozen";

    const svcRows = catalog
      .map((s) => {
        const isOverridden = Object.prototype.hasOwnProperty.call(svcOverrides, s.key);
        const curVal = isOverridden ? (svcOverrides[s.key] ? "on" : "off") : "default";
        const effLabel = (ent.enabled_services || []).includes(s.key) ? "ON" : "OFF";
        return `<div class="retailer-svc-row">
          <span><strong>${escHtml(s.label)}</strong> <small>(${effLabel})</small></span>
          <select data-svc-key="${escHtml(s.key)}">
            <option value="default" ${curVal === "default" ? "selected" : ""}>Default</option>
            <option value="on" ${curVal === "on" ? "selected" : ""}>Allow</option>
            <option value="off" ${curVal === "off" ? "selected" : ""}>Block</option>
          </select>
        </div>`;
      })
      .join("");

    const modeSelect = (key, label, currentVal) => {
      const ovVal = payOverrides[key];
      const ov = ovVal === true ? "on" : ovVal === false ? "off" : "default";
      return `<label>${escHtml(label)} (${currentVal ? "ON" : "OFF"})
        <select data-mode-key="${escHtml(key)}">
          <option value="default" ${ov === "default" ? "selected" : ""}>Default</option>
          <option value="on" ${ov === "on" ? "selected" : ""}>Allow</option>
          <option value="off" ${ov === "off" ? "selected" : ""}>Block</option>
        </select>
      </label>`;
    };

    host.innerHTML = `
      <div class="retailer-admin-box">
        <div class="retailer-wallet-bar">
          <div>
            <strong>Wallet: ${inr(w.available)} available</strong>
            ${Number(w.held || 0) > 0 ? `<small> · ${inr(w.held)} held</small>` : ""}
            <div style="font-size:12px;color:var(--muted)">Daily used ${inr(w.daily_used)} / ${inr(w.daily_debit_limit)} · Per txn ${inr(w.per_txn_limit)} · PIN: ${w.has_pin ? "Set" : "Not set"}</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button type="button" class="btn-xs ${frozen ? "primary" : "danger"}" data-ret-freeze>${frozen ? "Unfreeze wallet" : "Freeze wallet"}</button>
            <button type="button" class="btn-xs" data-ret-reset-pin>Reset PIN</button>
          </div>
        </div>
        <div class="policy-limits">
          <label>Quick adjust (CR/DR)<select data-ret-adj-dir><option value="CR">Credit (+)</option><option value="DR">Debit (-)</option></select></label>
          <label>Amount (₹)<input type="number" step="0.01" min="0.01" data-ret-adj-amt placeholder="500.00" /></label>
          <label>Reason<input type="text" data-ret-adj-reason placeholder="Settlement / adjustment" /></label>
          <button type="button" class="btn-xs primary" data-ret-adj-go>Apply CR/DR</button>
        </div>
        ${(Array.isArray(payload.pending_adjustments) ? payload.pending_adjustments : []).map((row) => `<div class="note">₹${escHtml(row.amount)} ${escHtml(row.direction)} is waiting for a second admin. Requested by ${escHtml(row.requested_by)}.
          <button type="button" class="btn-xs primary" data-adj-review="approve" data-adjustment-id="${escHtml(row.adjustment_id)}">Approve</button>
          <button type="button" class="btn-xs" data-adj-review="reject" data-adjustment-id="${escHtml(row.adjustment_id)}">Reject</button>
        </div>`).join("")}
        <div>
          <strong style="font-size:12px;display:block;margin-bottom:6px">Assigned services (overrides default policy)</strong>
          <div class="retailer-service-grid">${svcRows}</div>
        </div>
        <div class="policy-limits">
          ${modeSelect("allow_wallet_pay", "Wallet Pay", modes.wallet_pay)}
          ${modeSelect("allow_pg_pay", "Direct PG Pay", modes.pg_pay)}
          ${modeSelect("allow_pg_topup", "PG Wallet Top-up", modes.pg_topup)}
        </div>
        <div style="display:flex;justify-content:flex-end">
          <button type="button" class="btn-xs primary" data-ret-save-ent>Save service &amp; payment permissions</button>
        </div>
      </div>
    `;

    host.querySelector("[data-ret-freeze]")?.addEventListener("click", async () => {
      const reason = frozen ? "Admin unfreeze" : (window.prompt("Reason to freeze wallet:", "Compliance review") || "Admin freeze");
      const res = await call("/api/auth/desk/wallets/controls", {
        email,
        status: frozen ? "active" : "frozen",
        freeze_reason: frozen ? "" : reason,
      });
      if (!res.ok) return notify(res.data.error || "Could not update wallet status.");
      notify(frozen ? "Wallet unfrozen." : "Wallet frozen.");
      const ref = await call("/api/auth/desk/wallets?email=" + encodeURIComponent(email));
      renderRetailerControls(email, ref.ok ? ref.data : null);
    });

    host.querySelectorAll("[data-adj-review]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        const res = await call("/api/auth/desk/wallets/adjust-review", {
          adjustment_id: button.dataset.adjustmentId,
          decision: button.dataset.adjReview,
        });
        button.disabled = false;
        if (!res.ok) return notify(res.data.error || "Could not review the adjustment.");
        notify(button.dataset.adjReview === "approve" ? "Adjustment applied." : "Adjustment rejected.");
        const ref = await call("/api/auth/desk/wallets?email=" + encodeURIComponent(email));
        renderRetailerControls(email, ref.ok ? ref.data : null);
      });
    });

    host.querySelector("[data-ret-reset-pin]")?.addEventListener("click", async () => {
      const res = await call("/api/auth/desk/wallets/controls", { email, reset_pin: true });
      if (!res.ok) return notify(res.data.error || "Could not reset PIN.");
      notify("Wallet PIN cleared. Retailer must set a new PIN.");
      const ref = await call("/api/auth/desk/wallets?email=" + encodeURIComponent(email));
      renderRetailerControls(email, ref.ok ? ref.data : null);
    });

    host.querySelector("[data-ret-adj-go]")?.addEventListener("click", async () => {
      const direction = host.querySelector("[data-ret-adj-dir]")?.value || "CR";
      const amount = host.querySelector("[data-ret-adj-amt]")?.value || "";
      const reason = host.querySelector("[data-ret-adj-reason]")?.value || "";
      const button = host.querySelector("[data-ret-adj-go]");
      if (button) button.disabled = true;
      const res = await call(
        "/api/auth/desk/wallets/adjust",
        { email, direction, amount, reason },
        { "Idempotency-Key": moneyKey() },
      );
      if (button) button.disabled = false;
      if (!res.ok) return notify(res.data.error || "Adjustment failed.");
      if (res.data.pending) return notify(`₹${amount} ${direction} is waiting for a second admin.`);
      notify(`Wallet ${direction} ₹${amount} applied.`);
      const ref = await call("/api/auth/desk/wallets?email=" + encodeURIComponent(email));
      renderRetailerControls(email, ref.ok ? ref.data : null);
    });

    host.querySelector("[data-ret-save-ent]")?.addEventListener("click", async () => {
      const service_overrides = {};
      host.querySelectorAll("[data-svc-key]").forEach((sel) => {
        if (sel.value === "on") service_overrides[sel.dataset.svcKey] = true;
        else if (sel.value === "off") service_overrides[sel.dataset.svcKey] = false;
        else service_overrides[sel.dataset.svcKey] = null;
      });
      const body = { email, service_overrides };
      host.querySelectorAll("[data-mode-key]").forEach((sel) => {
        if (sel.value === "on") body[sel.dataset.modeKey] = true;
        else if (sel.value === "off") body[sel.dataset.modeKey] = false;
        else body[sel.dataset.modeKey] = null;
      });
      const res = await call("/api/auth/desk/entitlements/retailer", body);
      if (!res.ok) return notify(res.data.error || "Could not save permissions.");
      notify("Retailer services & payment modes updated.");
      const ref = await call("/api/auth/desk/wallets?email=" + encodeURIComponent(email));
      renderRetailerControls(email, ref.ok ? ref.data : null);
    });
  }

  let verifyFilter = "all";
  let pendingSignups = [];
  let verifiedAccounts = [];

  function verifyCheckDefs(row) {
    const defs = [
      { key: "email_ok", label: "Email" },
      { key: "mobile_ok", label: "SMS" },
    ];
    if (row.role === "retailer") {
      defs.push({ key: "aadhaar_ok", label: "DigiLocker" });
      defs.push({ key: "pan_ok", label: "PAN" });
    }
    return defs;
  }

  function checkStatus(row, def) {
    if (!row[def.key]) return "pending";
    return "passed";
  }

  function checkCaption(row, def) {
    const status = checkStatus(row, def);
    if (def.key === "mobile_ok" && row.mobile_last4) {
      return def.label + " ····" + row.mobile_last4 + " · " + (status === "passed" ? "Verified" : "Pending");
    }
    return def.label + " · " + (status === "passed" ? "Verified" : "Pending");
  }

  function formatVerifiedWhen(row) {
    if (!row.verified_at) return "Not recorded";
    return new Date(row.verified_at * 1000).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  }

  function accountReference(row, state) {
    if (state !== "verified") {
      const source = String(row.id || "").replace(/[^A-Za-z0-9]/g, "").toUpperCase();
      return "Application ID APP00" + (source.slice(-8) || "PENDING");
    }
    return "Account ID " + roleAccountId(row, row.role);
  }

  function checkFacts(row, def) {
    const status = checkStatus(row, def);
    const when = formatVerifiedWhen(row);
    if (def.key === "email_ok") {
      return [
        { term: "Status", value: status === "passed" ? "Verified" : "Pending" },
        { term: "Email address", value: row.email || "—" },
        { term: "Method", value: "Email one-time code during signup" },
        { term: "Recorded on desk", value: when },
      ];
    }
    if (def.key === "mobile_ok") {
      return [
        { term: "Status", value: status === "passed" ? "Verified" : "Pending" },
        { term: "Mobile", value: row.mobile_last4 ? "+91 ····" + row.mobile_last4 : "Last four not stored" },
        { term: "Method", value: "SMS one-time code during signup" },
        { term: "Recorded on desk", value: when },
      ];
    }
    if (def.key === "aadhaar_ok") {
      return [
        { term: "Status", value: status === "passed" ? "Verified" : "Pending" },
        { term: "DigiLocker session", value: row.digilocker_ref || "Session id not stored for this account" },
        { term: "Provider", value: "Cashfree Secure ID" },
        { term: "Recorded on desk", value: when },
      ];
    }
    if (def.key === "pan_ok") {
      return [
        { term: "Status", value: status === "passed" ? "Verified" : "Pending" },
        { term: "PAN on file", value: row.pan_mask || "Masked PAN not stored for this account" },
        { term: "Name on PAN", value: row.pan_name_hint || "Name not stored for this account" },
        { term: "Provider", value: "Cashfree PAN verification" },
        { term: "Recorded on desk", value: when },
      ];
    }
    return [{ term: "Status", value: status }];
  }

  async function hydrateRowForDetail(row) {
    if (!row.user_id) return row;
    const file = await call("/api/auth/desk/users/file?user_id=" + encodeURIComponent(row.user_id));
    if (!file.ok) return row;
    const stored = (file.data.profiles || []).find((entry) => entry.role === row.role);
    return Object.assign({}, row, stored || {}, { email: row.email || file.data.email });
  }

  function paintCheckDrawer(drawer, facts) {
    drawer.replaceChildren();
    const sheet = document.createElement("dl");
    sheet.className = "verify-record-sheet";
    facts.forEach((fact) => {
      const dt = document.createElement("dt");
      dt.textContent = fact.term;
      const dd = document.createElement("dd");
      dd.textContent = fact.value;
      sheet.append(dt, dd);
    });
    drawer.appendChild(sheet);
  }

  function attachCheckToggle(row, item, def) {
    const drawer = document.createElement("div");
    drawer.className = "verify-record-drawer";
    drawer.hidden = true;
    item.classList.add("is-clickable");
    item.setAttribute("role", "button");
    item.setAttribute("tabindex", "0");
    item.setAttribute("aria-expanded", "false");
    item.addEventListener("click", async (event) => {
      event.stopPropagation();
      const open = !item.classList.contains("is-open");
      document.querySelectorAll(".verify-record-item.is-open").forEach((node) => {
        if (node !== item) {
          node.classList.remove("is-open");
          node.setAttribute("aria-expanded", "false");
          node.querySelector(".verify-record-drawer")?.setAttribute("hidden", "");
        }
      });
      if (!open) {
        item.classList.remove("is-open");
        item.setAttribute("aria-expanded", "false");
        drawer.hidden = true;
        return;
      }
      item.classList.add("is-open");
      item.setAttribute("aria-expanded", "true");
      drawer.hidden = false;
      let detailRow = row;
      if (checkStatus(row, def) === "passed" && (!row.digilocker_ref || !row.pan_mask) && row.user_id) {
        detailRow = await hydrateRowForDetail(row);
      }
      paintCheckDrawer(drawer, checkFacts(detailRow, def));
    });
    item.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        item.click();
      }
    });
    return drawer;
  }

  function checkDetail(row, def) {
    const status = checkStatus(row, def);
    if (status !== "passed") return "Waiting for this step to complete.";
    if (def.key === "email_ok") {
      return row.email
        ? "Signup email " + row.email + " confirmed with a one-time code."
        : "Account email confirmed with a one-time code.";
    }
    if (def.key === "mobile_ok") {
      return row.mobile_last4
        ? "SMS OTP confirmed on +91 ····" + row.mobile_last4 + "."
        : "SMS one-time code confirmed at signup.";
    }
    if (def.key === "aadhaar_ok") {
      return row.digilocker_ref
        ? "DigiLocker consent via Cashfree. Session " + row.digilocker_ref + "."
        : "DigiLocker consent recorded through Cashfree Secure ID.";
    }
    if (def.key === "pan_ok") {
      const bits = [];
      if (row.pan_mask) bits.push("PAN " + row.pan_mask);
      if (row.pan_name_hint) bits.push("name " + row.pan_name_hint);
      return bits.length
        ? bits.join(" · ") + " · matched with Cashfree."
        : "PAN and name matched with Cashfree Secure ID.";
    }
    return "";
  }

  function verifyRecordBoard(row) {
    const board = document.createElement("div");
    board.className = "verify-record-board is-compact";
    const title = document.createElement("span");
    title.className = "verify-record-title";
    title.textContent = "Verification checks";
    board.append(title, verifyTrack(row));
    return board;
  }

  function verifyTrack(row) {
    const track = document.createElement("div");
    track.className = "verify-track";
    verifyCheckDefs(row).forEach((def) => {
      const step = document.createElement("span");
      const status = checkStatus(row, def);
      step.className = "verify-step " + (status === "passed" ? "is-done" : "is-wait");
      step.textContent = checkCaption(row, def);
      track.appendChild(step);
    });
    return track;
  }

  function buildVerifyRecord(row, state) {
    const record = document.createElement("div");
    record.className = "verify-record";
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    avatar.textContent = initials(row.email);
    const identity = document.createElement("div");
    identity.className = "verify-identity";
    const email = document.createElement("strong");
    email.textContent = row.email;
    email.title = row.email;
    const meta = document.createElement("div");
    meta.className = "verify-meta";
    const bits = [accountReference(row, state), roleLabel(row.role)];
    if (row.mobile_last4) bits.push("····" + row.mobile_last4);
    bits.push(state === "verified" ? "Verified" : "In progress");
    if (state === "verified" && row.verified_at) {
      bits.push(
        new Date(row.verified_at * 1000).toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        })
      );
    }
    bits.forEach((text, index) => {
      if (index) {
        const dot = document.createElement("span");
        dot.className = "dot";
        dot.textContent = "·";
        dot.setAttribute("aria-hidden", "true");
        meta.appendChild(dot);
      }
      if (index === 0) {
        const accountId = document.createElement("span");
        accountId.className = "verify-list-account-id";
        accountId.textContent = text;
        meta.appendChild(accountId);
      } else {
        meta.appendChild(document.createTextNode(text));
      }
    });
    identity.append(email, meta, verifyRecordBoard(row));
    record.append(avatar, identity);
    const note = document.createElement("p");
    note.className = "row-note";
    note.hidden = true;
    return { record, note };
  }

  let verifyProfilePerson = null;

  function closeVerifyProfile() {
    const panel = document.querySelector("[data-verify-profile]");
    if (panel) panel.hidden = true;
    verifyProfilePerson = null;
    document.querySelectorAll(".verify-item.is-selected").forEach((node) => {
      node.classList.remove("is-selected");
    });
  }

  function paintVerifyProfileChecks(row, profiles, selector) {
    const host = document.querySelector(selector || "[data-verify-profile-checks]");
    if (!host) return;
    host.replaceChildren();
    const stored = (profiles || []).find((entry) => entry.role === row.role);
    const profile = Object.assign({}, row, stored || {});
    verifyCheckDefs(profile).forEach((def) => {
      const wrap = document.createElement("div");
      wrap.className = "verify-profile-check-wrap";
      const card = document.createElement("div");
      const done = checkStatus(profile, def) === "passed";
      card.className = "verify-profile-check " + (done ? "is-done" : "");
      const title = document.createElement("b");
      title.textContent = def.label;
      const status = document.createElement("span");
      status.textContent = done ? "Passed" : "Pending";
      if (def.key === "mobile_ok" && profile.mobile_last4) {
        title.textContent = def.label + " ····" + profile.mobile_last4;
      }
      const detail = document.createElement("p");
      detail.className = "verify-profile-check-detail";
      detail.textContent = checkDetail(profile, def);
      card.append(title, detail, status);
      const drawer = attachCheckToggle(profile, card, def);
      wrap.append(card, drawer);
      host.appendChild(wrap);
    });
  }

  async function openVerifyProfile(row) {
    verifyProfilePerson = { id: row.user_id, email: row.email, roles: [row.role] };
    const panel = document.querySelector("[data-verify-profile]");
    const result = await call("/api/auth/desk/users/file?user_id=" + encodeURIComponent(row.user_id));
    if (!result.ok) {
      notify(result.data.error || "Could not load profile.", true);
      return;
    }
    const file = result.data;
    document.querySelectorAll(".verify-item.is-selected").forEach((node) => node.classList.remove("is-selected"));
    document.querySelectorAll("[data-verified] .verify-item, [data-signups] .verify-item").forEach((node) => {
      const strong = node.querySelector("strong");
      if (strong && strong.textContent === row.email) node.classList.add("is-selected");
    });
    panel.hidden = false;
    const avatar = document.querySelector("[data-verify-profile-avatar]");
    if (avatar) avatar.textContent = initials(file.email);
    document.querySelector("[data-verify-profile-email]").textContent = file.email;
    const meta = document.querySelector("[data-verify-profile-meta]");
    const mobile = (file.profiles || []).find((entry) => entry.role === row.role);
    meta.textContent = [
      roleLabel(row.role),
      mobile && mobile.mobile_last4 ? "····" + mobile.mobile_last4 : "",
      file.sign_in ? "Sign-in open" : "Sign-in closed",
    ].filter(Boolean).join(" · ");
    const accountId = document.querySelector("[data-verify-profile-id]");
    if (accountId) accountId.textContent = accountReference(Object.assign({}, row, { user_id: file.id || row.user_id }), "verified");
    const merged = Object.assign({}, row, (file.profiles || []).find((entry) => entry.role === row.role) || {});
    paintVerifyProfileChecks(merged, file.profiles);
    fillPlain(
      "[data-verify-profile-sessions]",
      file.sessions || [],
      "No open session.",
      (session) => [session.role, session.scope].filter(Boolean).join(" · ")
    );
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function paintVerifyFilters() {
    document.querySelectorAll("[data-verify-filter]").forEach((button) => {
      const key = button.dataset.verifyFilter;
      const on = key === verifyFilter;
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
      const count = button.querySelector("[data-verify-filter-count]");
      if (!count) return;
      if (key === "all") count.textContent = String(pendingSignups.length + verifiedAccounts.length);
      else if (key === "pending") count.textContent = String(pendingSignups.length);
      else if (key === "verified") count.textContent = String(verifiedAccounts.length);
    });
    document.querySelectorAll("[data-verify-panel]").forEach((panel) => {
      const key = panel.dataset.verifyPanel;
      panel.hidden = verifyFilter !== "all" && verifyFilter !== key;
    });
  }

  function paintVerifySummary() {
    const all = pendingSignups.concat(verifiedAccounts);
    const values = {
      total: all.length,
      pending: pendingSignups.length,
      verified: verifiedAccounts.length,
      retailer: all.filter((row) => row.role === "retailer").length,
    };
    Object.entries(values).forEach(([key, value]) => {
      const node = document.querySelector("[data-verify-stat-" + key + "]");
      if (node) node.textContent = String(value);
    });
  }

  function paintPendingSignups() {
    const list = fillList(
      "[data-signups]",
      pendingSignups,
      pendingSignups.length ? "" : "No signup in progress."
    );
    pendingSignups.forEach((row) => {
      const item = document.createElement("li");
      item.className = "verify-item";
      const { record, note } = buildVerifyRecord(row, "pending");
      function setRowNote(message, isError) {
        note.hidden = !message;
        note.textContent = message || "";
        note.classList.toggle("is-error", !!isError);
      }
      const actions = document.createElement("div");
      actions.className = "row-actions";
      if (!row.email_ok && !row.mobile_ok) {
        actions.append(actionButton("Resend", async () => {
          const sent = await call("/api/auth/signup/resend", { signup_id: row.id });
          if (!sent.ok) {
            setRowNote(sent.data.error || "Could not resend the codes.", true);
            return;
          }
          setRowNote("Codes sent again.", false);
          loadVerifications();
        }));
      }
      if (!row.email_ok || !row.mobile_ok || (row.role === "retailer" && !row.pan_ok)) {
        actions.append(actionButton("Continue", () => continueSignup(row), "primary btn-sm"));
      }
      actions.append(actionButton("Cancel", async () => {
        const ok = await askConfirm({
          title: "Cancel signup",
          body: "Cancel signup for " + row.email + "?",
          confirm: "Cancel signup",
          danger: true,
        });
        if (!ok) return;
        const removed = await call("/api/auth/signup/cancel", { signup_id: row.id });
        if (!removed.ok) {
          setRowNote(removed.data.error || "Could not cancel the signup.", true);
          return;
        }
        loadVerifications();
      }));
      item.append(record, actions);
      list.appendChild(item);
    });
  }

  function paintVerifiedAccounts() {
    const list = fillList(
      "[data-verified]",
      verifiedAccounts,
      verifiedAccounts.length ? "" : "No verified account yet."
    );
    verifiedAccounts.forEach((row) => {
      const item = document.createElement("li");
      item.className = "verify-item";
      const { record } = buildVerifyRecord(row, "verified");
      const actions = document.createElement("div");
      actions.className = "row-actions";
      actions.append(
        actionButton("View profile", () => openVerifyProfile(row), "primary btn-sm")
      );
      if (row.business_status === "pending_review") {
        actions.append(actionButton("Approve outlet", async () => {
          const reviewed = await call("/api/auth/desk/business-review", {
            email: row.email,
            decision: "approve",
          });
          if (!reviewed.ok) {
            notify(reviewed.data.error || "Could not approve the outlet.");
            return;
          }
          notify(row.email + " can sign in.");
          loadVerifications();
        }, "btn-sm"));
      }
      item.append(record, actions);
      list.appendChild(item);
    });
  }

  async function verifiedFromPeople() {
    const people = await call("/api/auth/desk/people");
    if (!people.ok) return [];
    const listed = [];
    for (const person of people.data.people || []) {
      const file = await call("/api/auth/desk/users/file?user_id=" + encodeURIComponent(person.id));
      const profiles = file.ok ? file.data.profiles || [] : [];
      for (const role of person.roles || []) {
        if (role !== "customer" && role !== "retailer") continue;
        const stored = profiles.find((entry) => entry.role === role);
        listed.push({
          user_id: person.id,
          email: person.email,
          role,
          mobile_last4: stored && stored.mobile_last4 ? stored.mobile_last4 : "",
          email_ok: stored ? !!stored.email_ok : true,
          mobile_ok: stored ? !!stored.mobile_ok : true,
          aadhaar_ok: stored ? !!stored.aadhaar_ok : role === "customer",
          pan_ok: stored ? !!stored.pan_ok : role === "customer",
          pan_mask: stored && stored.pan_mask ? stored.pan_mask : "",
          digilocker_ref: stored && stored.digilocker_ref ? stored.digilocker_ref : "",
          pan_name_hint: stored && stored.pan_name_hint ? stored.pan_name_hint : "",
          verified_at: person.created_at || 0,
        });
      }
    }
    listed.sort((a, b) => (b.verified_at || 0) - (a.verified_at || 0));
    return listed;
  }

  async function loadVerifications() {
    const result = await call("/api/auth/desk/signups");
    if (!result.ok) {
      pendingSignups = [];
      verifiedAccounts = [];
      const message = result.data.error || "Could not load verification.";
      fillList("[data-signups]", [], message);
      fillList("[data-verified]", [], message);
      document.querySelectorAll("[data-verify-count]").forEach((node) => { node.textContent = "0"; });
      const verifyTotal = document.querySelector("[data-verify-total]");
      if (verifyTotal) verifyTotal.textContent = "0 records";
      paintVerifySummary();
      paintVerifyFilters();
      return;
    }
    pendingSignups = result.data.pending || result.data.signups || [];
    verifiedAccounts = result.data.verified || [];
    if (!verifiedAccounts.length) {
      verifiedAccounts = await verifiedFromPeople();
    }
    document.querySelectorAll("[data-verify-count]").forEach((node) => {
      node.textContent = String(pendingSignups.length);
    });
    const verifyTotal = document.querySelector("[data-verify-total]");
    if (verifyTotal) {
      const n = pendingSignups.length + verifiedAccounts.length;
      verifyTotal.textContent = n + (n === 1 ? " record" : " records");
    }
    paintVerifySummary();
    paintVerifyFilters();
    paintPendingSignups();
    paintVerifiedAccounts();
  }

  function loadSignups() {
    return loadVerifications();
  }

  const AADHAAR_POLL_MS = 8000;
  let aadhaarPollTimer = null;

  function stopAadhaarPoll() {
    if (aadhaarPollTimer !== null) {
      clearInterval(aadhaarPollTimer);
      aadhaarPollTimer = null;
    }
  }

  function startAadhaarPoll(signupId, onAuthenticated, onFailed) {
    stopAadhaarPoll();
    if (!signupId) return;
    const tick = async () => {
      const result = await call("/api/auth/signup/aadhaar/status", { signup_id: signupId });
      if (!result.ok) return;
      if (result.data.state === "authenticated") {
        stopAadhaarPoll();
        onAuthenticated();
      } else if (result.data.state === "rejected") {
        stopAadhaarPoll();
        if (onFailed) onFailed(result.data.error || "DigiLocker was not completed.");
      }
    };
    void tick();
    aadhaarPollTimer = window.setInterval(tick, AADHAAR_POLL_MS);
  }

  const resumePanel = document.querySelector("[data-signup-resume]");
  const resumeForm = document.getElementById("resume-signup");
  let resumeRow = null;
  let resumeSignup = "";
  let resumeStep = "codes";

  function resumeStepFor(row) {
    if (!row.email_ok || !row.mobile_ok) return "codes";
    if (row.role !== "retailer") return "codes";
    if (!row.aadhaar_ok) return row.aadhaar_pending ? "aadhaar-done" : "aadhaar";
    if (!row.pan_ok) return "pan";
    return "business";
  }

  function resumeField(name) {
    return resumeForm.elements.namedItem(name);
  }

  function resumeError(message) {
    const node = resumeForm.querySelector("[data-resume-error]");
    node.hidden = !message;
    node.textContent = message || "";
  }

  function paintResumeProgress(row) {
    const list = document.querySelector("[data-resume-progress]");
    if (!list) return;
    list.replaceChildren();
    const steps = row.role === "retailer"
      ? [
          { key: "contact", label: "Email and SMS", done: row.email_ok && row.mobile_ok },
          { key: "aadhaar", label: "DigiLocker", done: row.aadhaar_ok },
          { key: "pan", label: "PAN", done: row.pan_ok },
          { key: "business", label: "GST and Udyam", done: false },
        ]
      : [{ key: "contact", label: "Email and SMS", done: row.email_ok && row.mobile_ok }];
    steps.forEach((step, index) => {
      const item = document.createElement("li");
      item.className = step.done ? "is-done" : "is-next";
      item.textContent = (index + 1) + ". " + step.label + (step.done ? " — done" : "");
      list.appendChild(item);
    });
  }

  function showResumeStep(step) {
    resumeStep = step;
    resumeForm.querySelectorAll("[data-resume]").forEach((node) => {
      node.hidden = node.dataset.resume !== step;
    });
    const labels = {
      codes: "Verify email and mobile",
      aadhaar: "Open DigiLocker",
      "aadhaar-done": "Continue to PAN",
      pan: "Check PAN",
      business: "Verify GST and Udyam",
    };
    const hints = {
      codes: "Enter both codes sent when this signup started. Use Resend on the queue if they expired.",
      aadhaar: "Opens DigiLocker. Email, mobile, and password stay as they were.",
      "aadhaar-done": "After DigiLocker shows success, this desk checks Cashfree every few seconds. You can also press Continue.",
      pan: "PAN is checked against the registry. The account stays closed until GST and Udyam match.",
      business: "Stand at the outlet. Cashfree must show an active GSTIN and a live Udyam for the same business.",
    };
    resumeForm.querySelector("[data-resume-submit]").textContent = labels[step] || "Continue";
    resumeForm.querySelector("[data-resume-hint]").textContent = hints[step] || "";
    if (step === "aadhaar-done") {
      startAadhaarPoll(
        resumeSignup,
        () => {
          resumeRow = Object.assign({}, resumeRow, { aadhaar_ok: true, aadhaar_pending: false });
          paintResumeProgress(resumeRow);
          notify("DigiLocker verified.");
          showResumeStep("pan");
        },
        (message) => resumeError(message)
      );
    } else {
      stopAadhaarPoll();
    }
    const needCodes = step === "codes";
    resumeField("email_code").required = needCodes;
    resumeField("sms_code").required = needCodes;
    const needPan = step === "pan";
    resumeField("pan").required = needPan;
    resumeField("pan_name").required = needPan;
    const needBusiness = step === "business";
    ["gstin", "udyam", "outlet_name", "lat", "lng"].forEach((name) => {
      const input = resumeField(name);
      if (input) input.required = needBusiness;
    });
  }

  function closeResume() {
    stopAadhaarPoll();
    resumePanel.hidden = true;
    resumeRow = null;
    resumeSignup = "";
    resumeForm.reset();
    resumeError("");
    const link = resumeForm.querySelector("[data-resume-link]");
    if (link) {
      link.hidden = true;
      link.textContent = "";
      link.removeAttribute("href");
    }
  }

  function openResumeSignup(row) {
    resumeRow = row;
    resumeSignup = row.id;
    room("verification");
    resumePanel.hidden = false;
    const roleName = row.role === "customer" ? "ParkPe customer" : "PaySwap retailer";
    const tail = row.mobile_last4 ? " · mobile ····" + row.mobile_last4 : "";
    document.querySelector("[data-resume-summary]").textContent =
      row.email + " · " + roleName + tail;
    paintResumeProgress(row);
    resumeError("");
    resumeForm.reset();
    showResumeStep(resumeStepFor(row));
    resumePanel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  async function finishResumeSignup(email, role) {
    closeResume();
    notify((email || "Account") + " is ready as " + (role === "customer" ? "ParkPe customer" : "PaySwap retailer") + ".");
    await loadPeople();
    loadSignups();
    room("verification");
  }

  function continueSignup(row) {
    openResumeSignup(row);
  }

  document.querySelector("[data-resume-close]")?.addEventListener("click", () => {
    closeResume();
    loadVerifications();
  });

  document.querySelector("[data-verify-profile-close]")?.addEventListener("click", closeVerifyProfile);
  document.querySelector("[data-verify-profile-users]")?.addEventListener("click", () => {
    if (!verifyProfilePerson) return;
    room("people");
    openFile(verifyProfilePerson);
  });

  resumeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    resumeError("");
    if (!resumeSignup || !resumeRow) return;
    const role = resumeRow.role;
    if (resumeStep === "codes") {
      const contact = await call("/api/auth/signup/contact", {
        signup_id: resumeSignup,
        email_code: resumeField("email_code").value,
        sms_code: resumeField("sms_code").value,
      });
      if (!contact.ok) return resumeError(contact.data.error || "Verification did not succeed.");
      if (contact.data.account_ready) {
        return finishResumeSignup(resumeRow.email, role);
      }
      resumeRow = Object.assign({}, resumeRow, { email_ok: true, mobile_ok: true });
      paintResumeProgress(resumeRow);
      showResumeStep("aadhaar");
      return;
    }
    if (resumeStep === "aadhaar") {
      const sent = await call("/api/auth/signup/aadhaar", { signup_id: resumeSignup });
      if (!sent.ok || !sent.data.url) return resumeError(sent.data.error || "Verification did not succeed.");
      const link = resumeForm.querySelector("[data-resume-link]");
      link.hidden = false;
      link.href = sent.data.url;
      link.textContent = sent.data.url;
      window.open(sent.data.url, "_blank", "noopener");
      resumeRow = Object.assign({}, resumeRow, { aadhaar_pending: true });
      showResumeStep("aadhaar-done");
      return;
    }
    if (resumeStep === "aadhaar-done") {
      const confirmed = await call("/api/auth/signup/aadhaar/confirm", { signup_id: resumeSignup });
      if (!confirmed.ok) return resumeError(confirmed.data.error || "Verification did not succeed.");
      resumeRow = Object.assign({}, resumeRow, { aadhaar_ok: true, aadhaar_pending: false });
      paintResumeProgress(resumeRow);
      showResumeStep("pan");
      return;
    }
    if (resumeStep === "pan") {
      const checked = await call("/api/auth/signup/pan", {
        signup_id: resumeSignup,
        pan: resumeField("pan").value,
        name: resumeField("pan_name").value,
      });
      if (!checked.ok || !checked.data.business_required) {
        return resumeError(checked.data.error || "Verification did not succeed.");
      }
      resumeRow = Object.assign({}, resumeRow, { pan_ok: true });
      paintResumeProgress(resumeRow);
      showResumeStep("business");
      return;
    }
    if (resumeField("location_source").value !== "desk") {
      return resumeError("Capture this desk's location before continuing.");
    }
    const opened = await call("/api/auth/signup/business", {
      signup_id: resumeSignup,
      gstin: resumeField("gstin").value,
      udyam: resumeField("udyam").value,
      outlet_name: resumeField("outlet_name").value,
      lat: resumeField("lat").value,
      lng: resumeField("lng").value,
      location_source: "desk",
    });
    if (!opened.ok || !opened.data.account_ready) {
      return resumeError(opened.data.error || "Business verification did not succeed.");
    }
    notify("Outlet is waiting for approval. Sign-in stays closed until you approve it.");
    return finishResumeSignup(resumeRow.email, "retailer");
  });

  document.querySelector("[data-resume-locate]")?.addEventListener("click", () => {
    captureDeskLocation(resumeField("lat"), resumeField("lng"), resumeField("location_source"), resumeError);
  });

  const SERVICE_ICONS = {
    kaleyra: "✉",
    email: "@",
    cashfree: "◇",
    payu: "₹",
    pg: "⌁",
    hub_api: "⌘",
    bbps: "₹",
    parking: "P",
  };

  function serviceStatusClass(state) {
    if (state === "warn") return "status warn";
    if (state === "down") return "status down";
    if (state === "stub") return "status stub";
    return "status";
  }

  function paintServices(services) {
    const grid = document.querySelector("[data-services-grid]");
    if (!grid) return;
    grid.replaceChildren();
    if (!services.length) {
      const empty = document.createElement("article");
      empty.className = "card service-card";
      empty.textContent = "No service metadata available.";
      grid.appendChild(empty);
      return;
    }
    services.forEach((svc) => {
      const card = document.createElement("article");
      card.className = "card service-card";

      const icon = document.createElement("div");
      icon.className = "service-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = SERVICE_ICONS[svc.id] || "▣";

      const body = document.createElement("div");
      const head = document.createElement("div");
      head.className = "service-card-head";
      const title = document.createElement("h2");
      title.textContent = svc.name || "Service";
      const status = document.createElement("span");
      status.className = serviceStatusClass(svc.state);
      status.textContent = svc.status_label || "Unknown";
      head.append(title, status);

      const summary = document.createElement("p");
      summary.textContent = [svc.kind, svc.summary].filter(Boolean).join(" · ");
      body.append(head, summary);

      const routes = document.createElement("div");
      routes.className = "service-routes";
      (svc.routes || []).forEach((route) => {
        const chip = document.createElement("span");
        chip.className = "service-route";
        chip.textContent = route;
        routes.appendChild(chip);
      });

      const foot = document.createElement("div");
      foot.className = "service-foot";
      const last = document.createElement("span");
      if (svc.last_call) {
        const lc = svc.last_call;
        const parts = [
          "Last: " + resultLabel(lc.outcome),
          lc.status ? String(lc.status) : "",
          lc.duration_ms || lc.duration_ms === 0 ? lc.duration_ms + " ms" : "",
        ].filter(Boolean);
        last.textContent = parts.join(" · ");
      } else {
        last.textContent = "No calls recorded yet.";
      }
      const openLogs = actionButton("View in Logs →", () => {
        logApiService = svc.log_filter || "all";
        logPages.api = 0;
        room("logs");
      });
      foot.append(last, openLogs);

      card.append(icon, body, routes, foot);
      grid.appendChild(card);
    });
  }

  async function loadServices() {
    const result = await call("/api/auth/desk/services");
    if (!result.ok) {
      const grid = document.querySelector("[data-services-grid]");
      if (grid) {
        grid.replaceChildren();
        const card = document.createElement("article");
        card.className = "card service-card";
        card.textContent = result.data.error || "Could not load services.";
        grid.appendChild(card);
      }
      return;
    }
    paintServices(result.data.services || []);
  }

  async function loadProcesses() {
    const result = await call("/api/auth/desk/processes");
    const processes = result.ok ? result.data.processes || [] : [];
    const list = fillList(
      "[data-processes]",
      processes,
      result.ok ? "No processes reported." : (result.data.error || "Could not read the processes.")
    );
    processes.forEach((row) => {
      const item = document.createElement("li");
      const line = document.createElement("span");
      line.textContent = row.name + " · " + row.port + " · " + (row.up ? "up" : "down");
      item.appendChild(line);
      if (row.url) {
        const link = document.createElement("a");
        link.href = row.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = "Open";
        item.appendChild(link);
      }
      list.appendChild(item);
    });
  }

  function paintHubList(selector, rows, empty, label) {
    const list = fillList(selector, rows, empty);
    rows.forEach((row) => {
      const item = document.createElement("li");
      item.appendChild(document.createElement("span")).textContent = label(row);
      list.appendChild(item);
    });
    return list;
  }

  async function loadParkpe() {
    if (!peopleRows.length) await loadPeople();
    const result = await call("/api/auth/desk/parkpe");
    const sessions = result.ok ? result.data.sessions || [] : [];
    const list = paintHubList(
      "[data-parkpe]",
      sessions,
      result.ok ? "No stored ParkPe session yet." : (result.data.error || "Could not load ParkPe."),
      (row) => [accountIdForEmail(row.actor, "customer"), row.reference, row.actor, row.site_code, row.bay, row.vehicle, row.state].filter(Boolean).join(" · ")
    );
    if (!result.ok) return;
    sessions.forEach((row, index) => {
      if (row.state === "closed") return;
      const item = list.children[index];
      if (!item) return;
      item.appendChild(actionButton("Mark closed", async () => {
        const closed = await call("/api/auth/desk/parkpe/close", { reference: row.reference });
        if (!closed.ok) return;
        loadParkpe();
      }));
    });
  }

  let payswapView = "hub";
  let econView = "hub";
  let payswapPolicyCache = null;

  function showPayswapView(name) {
    payswapView = name || "hub";
    if (payswapView !== "commission") econView = "hub";
    document.querySelectorAll("[data-payswap-view]").forEach((node) => {
      node.hidden = node.dataset.payswapView !== payswapView;
    });
    if (currentRoom === "payswap") {
      document.getElementById("crumb").textContent = deskCrumb("payswap");
      writeDeskRoute();
    }
  }

  function fillDefaultPolicyForm(p) {
    const policyForm = document.getElementById("default-policy-form");
    if (!policyForm || !p) return;
    const catalog = p.catalog || [];
    const enabled = new Set(p.enabled_services || []);
    const boxes = policyForm.querySelector("[data-default-services-boxes]");
    if (boxes) {
      boxes.replaceChildren();
      if (!catalog.length) {
        boxes.innerHTML = `<p class="note empty-state">No counter services in the catalogue yet.</p>`;
      } else {
        catalog.forEach((svc) => {
          const lbl = document.createElement("label");
          lbl.className = "policy-check-tile";
          const cb = document.createElement("input");
          cb.type = "checkbox";
          cb.name = "svc";
          cb.value = svc.key;
          cb.checked = enabled.has(svc.key);
          const copy = document.createElement("span");
          copy.className = "policy-check-copy";
          const title = document.createElement("strong");
          title.textContent = svc.label || svc.key;
          const sub = document.createElement("small");
          sub.textContent = svc.key;
          copy.append(title, sub);
          lbl.append(cb, copy);
          boxes.appendChild(lbl);
        });
      }
    }
    ["allow_wallet_pay", "allow_pg_pay", "allow_pg_topup", "bbps_bulk_enabled"].forEach((k) => {
      const el = policyForm.elements[k];
      if (el) el.checked = Boolean(p[k]);
    });
    if (policyForm.elements.pg_provider) {
      const mode = String(p.pg_provider || "both").toLowerCase();
      policyForm.elements.pg_provider.value = ["cashfree", "payu", "both"].includes(mode) ? mode : "both";
    }
    if (policyForm.elements.bbps_pipe) {
      const pipe = String(p.bbps_pipe || "mobikwik").toLowerCase();
      policyForm.elements.bbps_pipe.value = ["mobikwik", "pipe_b"].includes(pipe) ? pipe : "mobikwik";
    }
    const limMap = {
      default_per_txn_limit: p.default_per_txn_limit_paise,
      default_daily_debit_limit: p.default_daily_debit_limit_paise,
      default_min_balance: p.default_min_balance_paise,
    };
    Object.entries(limMap).forEach(([k, paise]) => {
      const el = policyForm.elements[k];
      if (el && paise != null) el.value = Math.round(Number(paise) / 100);
    });
  }

  function paintBbpsCatStats(p) {
    const catalog = p?.bbps_catalog || [];
    const enabled = new Set(p?.enabled_bbps_categories || []);
    const allOn = Boolean(p?.bbps_categories_unrestricted);
    const enabledCount = allOn ? catalog.length : catalog.filter((cat) => enabled.has(cat.id)).length;
    const setText = (sel, txt) => {
      const el = document.querySelector(sel);
      if (el) el.textContent = txt;
    };
    setText("[data-bbps-cat-enabled]", String(enabledCount));
    setText("[data-bbps-cat-enabled-note]", allOn ? "All categories on" : `${enabledCount} of ${catalog.length} selected`);
    setText("[data-bbps-cat-total]", String(catalog.length));
    setText("[data-bbps-cat-total-note]", catalog.length ? "From Mobikwik sheet" : "Import sheet in Economics");
    setText("[data-bbps-cat-mode]", allOn ? "Show all" : "Curated");
  }

  let bbpsOpenCategory = "";

  function filterBbpsCatTiles() {
    const boxes = document.querySelector("[data-default-bbps-cats]");
    const q = String(document.querySelector("[data-bbps-cat-search]")?.value || "").trim().toLowerCase();
    const note = document.querySelector("[data-bbps-cat-filter-note]");
    if (!boxes) return;
    let visible = 0;
    boxes.querySelectorAll("[data-bbps-cat-card]").forEach((tile) => {
      const hay = String(tile.dataset.search || "").toLowerCase();
      const show = !q || hay.includes(q);
      tile.hidden = !show;
      if (show) visible += 1;
    });
    if (note) {
      note.textContent = q
        ? `${visible} categor${visible === 1 ? "y" : "ies"} match “${q}”.`
        : "Open a category to curate billers. Save categories applies the outer ticks.";
    }
  }

  function filterBbpsBillerTiles(panel) {
    if (!panel) return;
    const q = String(panel.querySelector("[data-bbps-biller-search]")?.value || "").trim().toLowerCase();
    let visible = 0;
    panel.querySelectorAll("[data-bbps-biller-tile]").forEach((tile) => {
      const hay = String(tile.dataset.search || "").toLowerCase();
      const show = !q || hay.includes(q);
      tile.hidden = !show;
      if (show) visible += 1;
    });
    const note = panel.querySelector("[data-bbps-biller-note]");
    if (note && q) note.textContent = `${visible} biller${visible === 1 ? "" : "s"} match the search.`;
  }

  function paintBbpsBillerPanel(panel, payload) {
    if (!panel || !payload) return;
    const list = panel.querySelector("[data-bbps-biller-list]");
    const allToggle = panel.querySelector("[data-bbps-biller-all]");
    const note = panel.querySelector("[data-bbps-biller-note]");
    if (!list) return;
    const billers = payload.billers || [];
    const unrestricted = Boolean(payload.unrestricted);
    if (allToggle) allToggle.checked = unrestricted;
    list.replaceChildren();
    if (!billers.length) {
      list.innerHTML = `<p class="note empty-state">No billers in this category.</p>`;
    } else {
      billers.forEach((b) => {
        const lbl = document.createElement("label");
        lbl.className = "policy-check-tile";
        lbl.dataset.bbpsBillerTile = "";
        lbl.dataset.search = `${b.name || ""} ${b.biller_id || ""} ${b.op || ""}`;
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.name = "bbps_biller";
        cb.value = b.biller_id;
        cb.checked = Boolean(b.allowed);
        cb.disabled = unrestricted;
        const copy = document.createElement("span");
        copy.className = "policy-check-copy";
        const title = document.createElement("strong");
        title.textContent = b.name || b.biller_id;
        const sub = document.createElement("small");
        sub.textContent = `${b.biller_id}${b.op ? " · op " + b.op : ""}`;
        copy.append(title, sub);
        lbl.append(cb, copy);
        list.appendChild(lbl);
      });
    }
    list.classList.toggle("is-dimmed", unrestricted);
    if (note) {
      note.textContent = unrestricted
        ? "All billers in this category are allowed."
        : `${payload.allowed_count || 0} of ${payload.total || billers.length} billers allowed.`;
    }
    filterBbpsBillerTiles(panel);
  }

  async function openBbpsCategoryBillers(catId) {
    const card = document.querySelector(`[data-bbps-cat-card="${CSS.escape(catId)}"]`);
    if (!card) return;
    document.querySelectorAll("[data-bbps-cat-panel]").forEach((panel) => {
      const parent = panel.closest("[data-bbps-cat-card]");
      if (parent && parent !== card) {
        panel.hidden = true;
        parent.querySelector("[data-bbps-cat-open]")?.classList.remove("is-on");
      }
    });
    const panel = card.querySelector("[data-bbps-cat-panel]");
    const openBtn = card.querySelector("[data-bbps-cat-open]");
    if (!panel) return;
    const willOpen = panel.hidden;
    panel.hidden = !willOpen;
    openBtn?.classList.toggle("is-on", willOpen);
    bbpsOpenCategory = willOpen ? catId : "";
    if (!willOpen) return;
    const list = panel.querySelector("[data-bbps-biller-list]");
    if (list) list.innerHTML = `<p class="note">Loading billers…</p>`;
    const res = await call(
      "/api/auth/desk/entitlements/default/bbps-billers?category=" + encodeURIComponent(catId) + "&limit=500",
    );
    if (!res.ok) {
      if (list) list.innerHTML = `<p class="note empty-state">${escHtml(res.data.error || "Could not load billers.")}</p>`;
      return;
    }
    paintBbpsBillerPanel(panel, res.data);
  }

  async function saveBbpsCategoryBillers(catId) {
    const card = document.querySelector(`[data-bbps-cat-card="${CSS.escape(catId)}"]`);
    const panel = card?.querySelector("[data-bbps-cat-panel]");
    if (!panel) return;
    const allOn = Boolean(panel.querySelector("[data-bbps-biller-all]")?.checked);
    const ids = allOn
      ? null
      : Array.from(panel.querySelectorAll('input[name="bbps_biller"]:checked')).map((el) => el.value);
    if (!allOn && !(ids || []).length) {
      return notify("Pick at least one biller, or turn on All billers in this category.");
    }
    const body = { bbps_biller_allowlist: { [catId]: ids } };
    const res = await call("/api/auth/desk/entitlements/default", body);
    if (!res.ok) return notify(res.data.error || "Could not save billers.");
    payswapPolicyCache = res.data;
    bbpsOpenCategory = catId;
    fillDefaultBbpsCats(res.data);
    notify(allOn ? `All ${catId} billers allowed.` : `${catId}: ${ids.length} billers allowed.`);
  }

  function fillDefaultBbpsCats(p) {
    const boxes = document.querySelector("[data-default-bbps-cats]");
    const unrestricted = document.querySelector("[data-bbps-unrestricted]");
    if (!boxes || !p) return;
    const catalog = p.bbps_catalog || [];
    const enabled = new Set(p.enabled_bbps_categories || []);
    const allOn = Boolean(p.bbps_categories_unrestricted);
    const openId = bbpsOpenCategory;
    if (unrestricted) unrestricted.checked = allOn;
    boxes.replaceChildren();
    if (!catalog.length) {
      boxes.innerHTML = `<div class="empty-state reports-empty"><strong>No BBPS categories loaded</strong><p>Import the Mobikwik B2B sheet from Economics, then return here.</p></div>`;
    } else {
      catalog.forEach((cat) => {
        const card = document.createElement("article");
        card.className = "bbps-cat-card";
        card.dataset.bbpsCatCard = cat.id;
        card.dataset.search = `${cat.label || ""} ${cat.id || ""}`;
        const total = Number(cat.count || 0);
        const restricted = Boolean(cat.biller_restricted);
        const allowedBillers = restricted ? Number(cat.allowed_billers || 0) : total;
        const billerNote = restricted
          ? `${allowedBillers.toLocaleString("en-IN")} of ${total.toLocaleString("en-IN")} billers allowed`
          : `${total.toLocaleString("en-IN")} billers · all allowed`;
        card.innerHTML = `
          <div class="bbps-cat-card-head">
            <label class="policy-check-tile bbps-cat-toggle">
              <input type="checkbox" name="bbps_cat" value="${escHtml(cat.id)}" ${allOn || enabled.has(cat.id) ? "checked" : ""} ${allOn ? "disabled" : ""} />
              <span class="policy-check-copy"><strong>${escHtml(cat.label || cat.id)}</strong><small>${escHtml(billerNote)}</small></span>
            </label>
            <button class="select" type="button" data-bbps-cat-open="${escHtml(cat.id)}">Billers</button>
          </div>
          <div class="bbps-cat-panel" data-bbps-cat-panel hidden>
            <div class="bbps-biller-toolbar">
              <label class="payswap-inline-check"><input type="checkbox" data-bbps-biller-all /> All billers in this category</label>
              <label class="bbps-cat-search">Search billers
                <input type="search" data-bbps-biller-search placeholder="Name or biller id…" autocomplete="off" />
              </label>
              <button class="primary" type="button" data-bbps-biller-save="${escHtml(cat.id)}">Save billers</button>
            </div>
            <p class="note bbps-biller-note" data-bbps-biller-note></p>
            <div class="policy-checks policy-checks-bbps" data-bbps-biller-list></div>
          </div>`;
        boxes.appendChild(card);
      });
      boxes.querySelectorAll("[data-bbps-cat-open]").forEach((btn) => {
        btn.addEventListener("click", () => openBbpsCategoryBillers(btn.dataset.bbpsCatOpen || ""));
      });
      boxes.querySelectorAll("[data-bbps-biller-save]").forEach((btn) => {
        btn.addEventListener("click", () => saveBbpsCategoryBillers(btn.dataset.bbpsBillerSave || ""));
      });
      boxes.querySelectorAll("[data-bbps-biller-all]").forEach((toggle) => {
        toggle.addEventListener("change", () => {
          const panel = toggle.closest("[data-bbps-cat-panel]");
          const on = Boolean(toggle.checked);
          panel?.querySelectorAll('input[name="bbps_biller"]').forEach((cb) => {
            cb.disabled = on;
            if (on) cb.checked = true;
          });
          panel?.querySelector("[data-bbps-biller-list]")?.classList.toggle("is-dimmed", on);
          const note = panel?.querySelector("[data-bbps-biller-note]");
          if (note) {
            note.textContent = on
              ? "All billers in this category are allowed."
              : "Curate the billers below, then save.";
          }
        });
      });
      boxes.querySelectorAll("[data-bbps-biller-search]").forEach((input) => {
        input.addEventListener("input", () => filterBbpsBillerTiles(input.closest("[data-bbps-cat-panel]")));
      });
    }
    boxes.classList.toggle("is-dimmed", false);
    boxes.querySelectorAll(".bbps-cat-toggle").forEach((el) => el.classList.toggle("is-dimmed", allOn));
    paintBbpsCatStats(p);
    filterBbpsCatTiles();
    if (openId && catalog.some((c) => c.id === openId)) {
      openBbpsCategoryBillers(openId);
    } else {
      bbpsOpenCategory = "";
    }
  }

  function fillRetailerSvcSelect() {
    const sel = document.querySelector("[data-retailer-svc-select]");
    if (!sel) return;
    const current = sel.value;
    const retailers = (peopleRows || []).filter((r) => (r.roles || [r.role]).includes("retailer"));
    sel.replaceChildren();
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "Select retailer…";
    sel.append(blank);
    retailers
      .slice()
      .sort((a, b) => String(a.email || "").localeCompare(String(b.email || "")))
      .forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r.email;
        const rid = roleAccountId(r, "retailer") || accountIdForEmail(r.email, "retailer");
        opt.textContent = rid ? `${rid} · ${r.email}` : r.email;
        sel.append(opt);
      });
    if (current && [...sel.options].some((o) => o.value === current)) sel.value = current;
  }

  let retailerSheetService = "bbps";
  let retailerSheetPage = 0;
  let retailerSheetRows = [];
  let retailerSheetEmail = "";
  const RETAILER_SHEET_PAGE = 10;

  function retailerRateLabel(row) {
    if (row.has_rate === false) return "No sheet rate";
    const value = String(row.rate_value ?? "");
    if (!value || value === "0" || value === "0.00") return "No sheet rate";
    return row.rate_type === "percent" ? `${value}%` : `₹${value}`;
  }

  function paintRetailerBillerSheet() {
    const box = document.querySelector("[data-retailer-biller-sheet]");
    if (!box) return;
    const rows = retailerSheetRows;
    if (!rows.length) {
      const label = retailerSheetService.toUpperCase();
      box.innerHTML = `<div class="commission-empty"><strong>No ${escHtml(label)} sheet yet</strong><p>Import the ${escHtml(label)} sheet in Economics. Then set what this retailer earns on each row.</p></div>`;
      return;
    }
    const pages = Math.max(1, Math.ceil(rows.length / RETAILER_SHEET_PAGE));
    retailerSheetPage = Math.min(retailerSheetPage, pages - 1);
    const slice = rows.slice(retailerSheetPage * RETAILER_SHEET_PAGE, (retailerSheetPage + 1) * RETAILER_SHEET_PAGE);
    const body = slice
      .map((row) => {
        const externalId = row.external_id || row.operator_id || row.bbps_op || "";
        const category = row.category || row.bbps_category || "";
        const name = row.bbps_name || row.operator_name || row.name || "Unnamed row";
        const custom = row.share_source === "biller";
        const value = custom && row.retailer_admin_share_percent != null ? String(row.retailer_admin_share_percent) : "";
        const placeholder = String(row.fallback_admin_share_percent ?? row.default_admin_share_percent ?? "");
        const source = custom ? "This biller" : row.share_source === "service" ? "Service default" : "Economics";
        return `<tr data-biller-id="${escHtml(externalId)}" data-biller-category="${escHtml(category)}">
          <td class="commission-biller-cell"><strong>${escHtml(name)}</strong><span class="mono">${escHtml(externalId)}</span></td>
          <td><span class="commission-category">${escHtml(category || "—")}</span></td>
          <td><div class="commission-fact is-set"><span>Economics</span><strong>${escHtml(retailerRateLabel(row))}</strong><small>Admin ${escHtml(String(row.default_admin_share_percent ?? "—"))}% · Retailer ${escHtml(String(row.default_retailer_share_percent ?? "—"))}%</small></div></td>
          <td>
            <span class="commission-percent-input">
              <input type="number" min="0" max="100" step="0.01" inputmode="decimal" data-biller-share placeholder="${escHtml(placeholder)}" value="${escHtml(value)}" />
              <b>%</b>
            </span>
            <small>${escHtml(source)} · blank inherits</small>
          </td>
          <td><div class="commission-fact is-settled"><span>This retailer</span><strong>${escHtml(String(row.effective_retailer_share_percent ?? "—"))}%</strong><small>Admin keeps ${escHtml(String(row.effective_admin_share_percent ?? "—"))}%</small></div></td>
          <td><div class="commission-row-actions">
            <button type="button" class="btn-xs primary" data-biller-save>Save</button>
            <button type="button" class="btn-xs" data-biller-clear ${custom ? "" : "disabled"}>Inherit</button>
          </div></td>
        </tr>`;
      })
      .join("");
    box.innerHTML = `<div class="commission-scroll"><table class="commission-table retailer-comm-sheet"><thead><tr>
        <th>Biller</th><th>Category</th><th>Economics sheet</th><th>Admin share for this retailer</th><th>Retailer earns</th><th></th>
      </tr></thead><tbody>${body}</tbody></table></div>
      <div data-retailer-sheet-pager></div>`;
    paintCommPager(box.querySelector("[data-retailer-sheet-pager]"), retailerSheetPage, rows.length, RETAILER_SHEET_PAGE, "retailer-sheet");
  }

  async function loadRetailerBillerSheet() {
    const box = document.querySelector("[data-retailer-biller-sheet]");
    const email = retailerSheetEmail;
    if (!box || !email) return;
    box.innerHTML = `<div class="commission-empty"><strong>Loading ${escHtml(retailerSheetService.toUpperCase())} sheet…</strong><p>Rates configured in Economics, with this retailer’s share on each row.</p></div>`;
    const qs = new URLSearchParams({
      email,
      sheet: retailerSheetService,
      limit: "200",
    });
    const q = String(document.querySelector("[data-retailer-sheet-q]")?.value || "").trim();
    const category = String(document.querySelector("[data-retailer-sheet-category]")?.value || "").trim();
    if (q) qs.set("q", q);
    if (category) qs.set("category", category);
    const res = await call("/api/auth/desk/commission/retailer?" + qs.toString());
    if (!res.ok) {
      box.innerHTML = `<div class="commission-empty"><strong>Could not load sheet</strong><p>${escHtml(res.data.error || "Try the sheet again.")}</p></div>`;
      return;
    }
    const catalogue = res.data.catalogue || {};
    retailerSheetRows = catalogue.rows || [];
    paintRetailerBillerSheet();
  }

  async function loadRetailerSvcPanel(email) {
    const host = document.querySelector("[data-retailer-svc-panel]");
    if (!host) return;
    if (!email) {
      host.innerHTML = `<div class="commission-empty"><strong>No retailer loaded</strong><p>Choose a retailer account above to open counter access and the commission sheet.</p></div>`;
      return;
    }
    host.innerHTML = `<div class="commission-empty"><strong>Loading account…</strong><p>${escHtml(email)}</p></div>`;
    const [entRes, walletRes] = await Promise.all([
      call("/api/auth/desk/entitlements/retailer?email=" + encodeURIComponent(email)),
      call("/api/auth/desk/wallets?email=" + encodeURIComponent(email)),
    ]);
    if (!entRes.ok) {
      host.innerHTML = `<div class="commission-empty"><strong>Could not load retailer</strong><p>${escHtml(entRes.data.error || "Entitlements request failed.")}</p></div>`;
      return;
    }
    const ent = entRes.data || {};
    const catalog = ent.bbps_catalog || [];
    const catOverrides = ent.bbps_category_overrides || {};
    const svcCatalog = ent.catalog || [];
    const svcOverrides = ent.service_overrides || {};
    const payOverrides = ent.payment_overrides || {};
    const modes = ent.payment_modes || {};
    const enabledSvcs = new Set(ent.enabled_services || []);
    const bbpsOn = enabledSvcs.has("bbps");
    const w = walletRes.ok ? walletRes.data.wallet || {} : {};
    const catRows = catalog
      .map((c) => {
        const isOv = Object.prototype.hasOwnProperty.call(catOverrides, c.id);
        const cur = isOv ? (catOverrides[c.id] ? "on" : "off") : "default";
        const eff = (ent.enabled_bbps_categories || []).includes(c.id) ? "ON" : "OFF";
        return `<div class="retailer-svc-row">
          <span><strong>${escHtml(c.label)}</strong> <small>(${eff})</small></span>
          <select data-bbps-cat-key="${escHtml(c.id)}" ${bbpsOn ? "" : "disabled"}>
            <option value="default" ${cur === "default" ? "selected" : ""}>Default</option>
            <option value="on" ${cur === "on" ? "selected" : ""}>Allow</option>
            <option value="off" ${cur === "off" ? "selected" : ""}>Block</option>
          </select>
        </div>`;
      })
      .join("");

    const productKeys = { bbps: 1, recharge: 1, vouchers: 1, dmt: 1, aeps: 1 };
    const svcRow = (s) => {
      const isOverridden = Object.prototype.hasOwnProperty.call(svcOverrides, s.key);
      const curVal = isOverridden ? (svcOverrides[s.key] ? "on" : "off") : "default";
      const effLabel = enabledSvcs.has(s.key) ? "ON" : "OFF";
      return `<div class="retailer-svc-row">
          <span><strong>${escHtml(s.label)}</strong> <small>${effLabel}</small></span>
          <select data-svc-key="${escHtml(s.key)}">
            <option value="default" ${curVal === "default" ? "selected" : ""}>Default</option>
            <option value="on" ${curVal === "on" ? "selected" : ""}>Allow</option>
            <option value="off" ${curVal === "off" ? "selected" : ""}>Block</option>
          </select>
        </div>`;
    };
    const productRows = svcCatalog.filter((s) => productKeys[s.key]).map(svcRow).join("");
    const deskRows = svcCatalog.filter((s) => !productKeys[s.key]).map(svcRow).join("");

    const modeSelect = (key, label, currentVal) => {
      const ovVal = payOverrides[key];
      const ov = ovVal === true ? "on" : ovVal === false ? "off" : "default";
      return `<label>${escHtml(label)} <small>${currentVal ? "ON" : "OFF"}</small>
        <select data-mode-key="${escHtml(key)}">
          <option value="default" ${ov === "default" ? "selected" : ""}>Default</option>
          <option value="on" ${ov === "on" ? "selected" : ""}>Allow</option>
          <option value="off" ${ov === "off" ? "selected" : ""}>Block</option>
        </select>
      </label>`;
    };

    const retailerId = accountIdForEmail(email, "retailer") || "—";
    const walletStatus = String(w.status || "—");
    const walletStatusClass = walletStatus.toLowerCase() === "active" ? "" : walletStatus.toLowerCase() === "blocked" ? "down" : "warn";
    const sheetTabs = [
      ["bbps", "BBPS"],
      ["recharge", "Recharge"],
      ["vouchers", "Vouchers"],
      ["dmt", "DMT"],
      ["aeps", "AEPS"],
    ]
      .map(
        ([key, label]) =>
          `<button type="button" class="${key === retailerSheetService ? "is-on" : ""}" data-retailer-sheet-service="${key}">${label}</button>`,
      )
      .join("");

    host.innerHTML = `
      <section class="card room-card retailer-identity-card">
        <div class="room-body retailer-identity">
          <div class="retailer-identity-main">
            <strong>${escHtml(email)}</strong>
            <span class="mono">${escHtml(retailerId)}</span>
            <span class="status ${walletStatusClass}">${escHtml(walletStatus)}</span>
          </div>
          <div class="retailer-identity-meta">
            <span>Wallet <strong>${inr(w.available || 0)}</strong></span>
            <button type="button" class="select" data-jump="people">Account Hub</button>
          </div>
        </div>
      </section>

      <section class="card room-card retailer-access-card">
        <div class="panel-head">
          <div>
            <h2>Counter access</h2>
            <p>Products, payment rails, and BBPS categories for ${escHtml(retailerId)}.</p>
          </div>
          <div class="room-actions">
            <button type="button" class="primary" data-retailer-svc-save>Save counter</button>
          </div>
        </div>
        <div class="room-body">
          <div class="segments retailer-access-tabs" role="tablist" aria-label="Counter access">
            <button type="button" class="is-on" data-retailer-access-tab="products" aria-selected="true">Products</button>
            <button type="button" data-retailer-access-tab="rails" aria-selected="false">Payment rails</button>
            <button type="button" data-retailer-access-tab="bbps" aria-selected="false">BBPS categories</button>
          </div>
          <div class="retailer-access-pane is-active" data-retailer-access-pane="products">
            <p class="note">Counter products this retailer can open.</p>
            <div class="retailer-service-grid">${productRows}</div>
            <p class="note retailer-access-subhead">Bulk bills (Excel)</p>
            <div class="policy-limits retailer-rail-limits">
              <label>Bulk bills
                <select data-bbps-bulk ${bbpsOn ? "" : "disabled"}>
                  <option value="default" ${ent.bbps_bulk_override == null ? "selected" : ""}>Default (${ent.bbps_bulk_enabled ? "on" : "off"})</option>
                  <option value="on" ${ent.bbps_bulk_override === true ? "selected" : ""}>Allow</option>
                  <option value="off" ${ent.bbps_bulk_override === false ? "selected" : ""}>Block</option>
                </select>
              </label>
              <label>BBPS pipe
                <select data-bbps-pipe ${bbpsOn ? "" : "disabled"}>
                  <option value="default" ${!ent.bbps_pipe_override ? "selected" : ""}>Default (${escHtml(ent.bbps_pipe || "mobikwik")})</option>
                  <option value="mobikwik" ${ent.bbps_pipe_override === "mobikwik" ? "selected" : ""}>Mobikwik</option>
                  <option value="pipe_b" ${ent.bbps_pipe_override === "pipe_b" ? "selected" : ""}>Pipe B</option>
                </select>
              </label>
            </div>
            <p class="hint">${bbpsOn
              ? `Effective now: Bulk bills ${ent.bbps_bulk_enabled ? "ON" : "OFF"} · pipe ${escHtml(ent.bbps_pipe || "mobikwik")}. Save counter after changing.`
              : "Turn Bill Pay (BBPS) to Allow before Bulk bills can show on the counter."}</p>
            <p class="note retailer-access-subhead">Always on the desk</p>
            <div class="retailer-service-grid retailer-service-grid-quiet">${deskRows}</div>
          </div>
          <div class="retailer-access-pane" data-retailer-access-pane="rails" hidden>
            <p class="note">Wallet and PG permissions for this account.</p>
            <div class="policy-limits retailer-rail-limits">
              ${modeSelect("allow_wallet_pay", "Wallet Pay", modes.wallet_pay)}
              ${modeSelect("allow_pg_pay", "Direct PG Pay", modes.pg_pay)}
              ${modeSelect("allow_pg_topup", "PG Wallet Top-up", modes.pg_topup)}
            </div>
          </div>
          <div class="retailer-access-pane" data-retailer-access-pane="bbps" hidden>
            <p class="note">${bbpsOn
              ? "Bill categories this retailer can open. Default inherits BBPS management."
              : "Bill Pay is blocked — category overrides apply only after BBPS is Allow or Default-on."}</p>
            <div class="retailer-service-grid ${bbpsOn ? "" : "is-dimmed"}">${catRows || `<p class="note">No BBPS categories in catalogue.</p>`}</div>
          </div>
        </div>
      </section>

      <section class="card room-card retailer-commission-card">
        <div class="panel-head retailer-sheet-head">
          <div>
            <h2>Commission sheet</h2>
            <p>What ${escHtml(retailerId)} earns per row. Blank inherits Economics.</p>
          </div>
          <div class="room-actions">
            <div class="segments" data-retailer-sheet-tabs aria-label="Commission sheet">${sheetTabs}</div>
            <button type="button" class="select" data-payswap-open="commission" data-econ-target="commission">Economics default</button>
          </div>
        </div>
        <div class="room-body commission-catalogue-toolbar">
          <div class="commission-rate-filters">
            <label>Category <input type="search" data-retailer-sheet-category placeholder="e.g. PREPAID" /></label>
            <label>Search biller <input type="search" data-retailer-sheet-q placeholder="Name or biller id" /></label>
          </div>
        </div>
        <div class="table-wrap" data-retailer-biller-sheet>
          <div class="commission-empty"><strong>Loading sheet…</strong><p>Fetching this service’s commission rows.</p></div>
        </div>
      </section>`;

    retailerSheetEmail = email;
    host.querySelectorAll("[data-retailer-access-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.retailerAccessTab || "products";
        host.querySelectorAll("[data-retailer-access-tab]").forEach((node) => {
          const on = node === btn;
          node.classList.toggle("is-on", on);
          node.setAttribute("aria-selected", on ? "true" : "false");
        });
        host.querySelectorAll("[data-retailer-access-pane]").forEach((pane) => {
          const on = pane.dataset.retailerAccessPane === tab;
          pane.classList.toggle("is-active", on);
          pane.hidden = !on;
        });
      });
    });
    host.querySelectorAll("[data-retailer-sheet-service]").forEach((btn) => {
      btn.addEventListener("click", () => {
        retailerSheetService = btn.dataset.retailerSheetService || "bbps";
        retailerSheetPage = 0;
        host.querySelectorAll("[data-retailer-sheet-service]").forEach((node) => {
          node.classList.toggle("is-on", node === btn);
        });
        loadRetailerBillerSheet();
      });
    });
    const reloadSheet = () => {
      retailerSheetPage = 0;
      loadRetailerBillerSheet();
    };
    host.querySelector("[data-retailer-sheet-q]")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") reloadSheet();
    });
    host.querySelector("[data-retailer-sheet-category]")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") reloadSheet();
    });
    host.querySelector("[data-retailer-sheet-category]")?.addEventListener("change", reloadSheet);
    loadRetailerBillerSheet();

    host.querySelectorAll("[data-payswap-open]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const next = btn.dataset.payswapOpen || "hub";
        showPayswapView(next);
        if (next === "commission") {
          const econTarget = btn.dataset.econTarget || "";
          if (econTarget && ECON_VIEWS.has(econTarget)) openEconView(econTarget);
          else loadCommissionDesk();
        }
      });
    });

    host.querySelector("[data-retailer-svc-save]")?.addEventListener("click", async () => {
      const bbps_category_overrides = {};
      host.querySelectorAll("[data-bbps-cat-key]").forEach((sel) => {
        if (sel.disabled) return;
        if (sel.value === "on") bbps_category_overrides[sel.dataset.bbpsCatKey] = true;
        else if (sel.value === "off") bbps_category_overrides[sel.dataset.bbpsCatKey] = false;
        else bbps_category_overrides[sel.dataset.bbpsCatKey] = null;
      });
      const service_overrides = {};
      host.querySelectorAll("[data-svc-key]").forEach((sel) => {
        if (sel.value === "on") service_overrides[sel.dataset.svcKey] = true;
        else if (sel.value === "off") service_overrides[sel.dataset.svcKey] = false;
        else service_overrides[sel.dataset.svcKey] = null;
      });
      const body = { email, service_overrides, bbps_category_overrides };
      host.querySelectorAll("[data-mode-key]").forEach((sel) => {
        if (sel.value === "on") body[sel.dataset.modeKey] = true;
        else if (sel.value === "off") body[sel.dataset.modeKey] = false;
        else body[sel.dataset.modeKey] = null;
      });
      const pipeSel = host.querySelector("[data-bbps-pipe]");
      if (pipeSel) body.bbps_pipe = pipeSel.value === "default" ? null : pipeSel.value;
      const bulkSel = host.querySelector("[data-bbps-bulk]");
      if (bulkSel) {
        if (bulkSel.value === "on") body.bbps_bulk_enabled = true;
        else if (bulkSel.value === "off") body.bbps_bulk_enabled = false;
        else body.bbps_bulk_enabled = null;
      }
      const res = await call("/api/auth/desk/entitlements/retailer", body);
      if (!res.ok) return notify(res.data.error || "Could not save retailer dashboard.");
      notify("Retailer dashboard saved — blocked services are gone from their counter.");
      loadRetailerSvcPanel(email);
    });
  }

  async function loadPayswapActivity() {
    const [txRes, voucherRes] = await Promise.all([
      call("/api/auth/desk/transactions?limit=50"),
      call("/api/auth/desk/payswap"),
    ]);
    const bbpsWrap = document.querySelector("[data-desk-bbps-table]");
    const rows = txRes.ok ? (txRes.data.bbps_transactions || []) : [];
    const pending = rows.filter((r) => r.state === "pending").length;
    const success = rows.filter((r) => r.state === "success").length;
    const volume = rows.reduce((sum, r) => sum + Number(r.amount || 0), 0);
    const setText = (sel, value) => {
      const el = document.querySelector(sel);
      if (el) el.textContent = value;
    };
    setText("[data-ps-bbps-count]", String(rows.length));
    setText("[data-ps-bbps-pending]", `${pending} pending`);
    setText("[data-ps-bbps-vol]", inr(volume));
    setText("[data-ps-bbps-success]", `${success} success`);
    if (bbpsWrap) {
      if (!rows.length) {
        bbpsWrap.innerHTML = `<p class="note">${txRes.ok ? "No BBPS transactions recorded yet." : escHtml(txRes.data.error || "Could not load BBPS transactions.")}</p>`;
      } else {
        const html = rows
          .map((r) => {
            const syncBtn = r.state === "pending"
              ? `<button type="button" class="btn-xs" data-sync-bbps="${escHtml(r.reference)}">Sync status</button>`
              : "";
            const rid = accountIdForEmail(r.user_id, "retailer") || r.user_id;
            const detail = r.error_message
              ? `<br><small class="is-danger">${escHtml(r.error_message)}</small>`
              : (r.vendor_txn_id ? `<br><small>Vendor: ${escHtml(r.vendor_txn_id)}</small>` : "");
            return `<tr>
              <td><strong class="mono">${escHtml(r.reference)}</strong><br><small>${escHtml(rid)} · ${escHtml(logTime(r.created_at))}</small></td>
              <td>${escHtml(r.biller || r.operator_id)}<br><small>${escHtml(r.account || "—")}</small></td>
              <td>${escHtml((r.payment_channel || "").toUpperCase())}</td>
              <td class="num"><strong>${inr(r.amount)}</strong></td>
              <td><span class="pill ${r.state === "success" ? "success" : r.state === "pending" ? "pending" : "failed"}">${escHtml(r.state)}</span>${detail}</td>
              <td><div class="desk-actions">${syncBtn}</div></td>
            </tr>`;
          })
          .join("");
        bbpsWrap.innerHTML = `<table class="desk-table"><thead><tr><th>Reference / Retailer</th><th>Biller / Consumer</th><th>Rail</th><th class="num">Amount</th><th>Status</th><th></th></tr></thead><tbody>${html}</tbody></table>`;
        bbpsWrap.querySelectorAll("[data-sync-bbps]").forEach((btn) => {
          btn.addEventListener("click", async () => {
            btn.disabled = true;
            const res = await call("/api/auth/desk/transactions/bbps-sync", { reference: btn.dataset.syncBbps });
            if (!res.ok) notify(res.data.error || "Could not sync status.");
            else notify(`BBPS ${btn.dataset.syncBbps}: ${res.data.state || "synced"}`);
            loadPayswapActivity();
          });
        });
      }
    }
    const orders = voucherRes.ok ? voucherRes.data.orders || [] : [];
    setText("[data-ps-voucher-count]", String(orders.length));
    setText("[data-ps-voucher-meta]", voucherRes.ok ? "Recent API orders" : "Could not load vouchers");
    paintHubList(
      "[data-payswap]",
      orders,
      voucherRes.ok ? "No stored PaySwap order yet." : (voucherRes.data.error || "Could not load PaySwap."),
      (row) => [accountIdForEmail(row.actor, "retailer"), row.reference, row.actor, row.brand, row.amount, row.state].filter(Boolean).join(" · ")
    );
  }

  async function loadPayswap() {
    if (!peopleRows.length) await loadPeople();
    showPayswapView(payswapView || "hub");
    const policyRes = await call("/api/auth/desk/entitlements/default");
    if (policyRes.ok) {
      payswapPolicyCache = policyRes.data;
      fillDefaultPolicyForm(policyRes.data);
      fillDefaultBbpsCats(policyRes.data);
    }
    fillRetailerSvcSelect();
    if (payswapView === "activity") await loadPayswapActivity();
    if (payswapView === "bulk") await loadBulkDesk();
    if (payswapView === "retailers") {
      const sel = document.querySelector("[data-retailer-svc-select]");
      if (sel && sel.value) await loadRetailerSvcPanel(sel.value);
    }
  }

  async function loadBulkDesk() {
    const q = (document.querySelector("[data-bulk-desk-q]")?.value || "").trim();
    const qs = q ? `?q=${encodeURIComponent(q)}&limit=50` : "?limit=50";
    const res = await call("/api/auth/desk/bbps/bulk" + qs);
    const wrap = document.querySelector("[data-bulk-desk-table]");
    if (!wrap) return;
    if (!res.ok) {
      wrap.innerHTML = `<p class="note">${escHtml(res.data.error || "Could not load bulk batches.")}</p>`;
      return;
    }
    const batches = res.data.batches || [];
    setText("[data-bulk-desk-count]", String(batches.length));
    const paid = batches.reduce((sum, b) => sum + Number(b.paid_total || 0), 0);
    const payOk = batches.reduce((sum, b) => sum + Number(b.pay_ok || 0), 0);
    const fetchFail = batches.reduce((sum, b) => sum + Number(b.fetch_fail || 0), 0);
    setText("[data-bulk-desk-paid]", inr(paid));
    setText("[data-bulk-desk-payok]", `${payOk} pay ok`);
    setText("[data-bulk-desk-fetchfail]", String(fetchFail));
    setText("[data-bulk-desk-meta]", batches.length ? "Recent uploads" : "No batches yet");
    if (!batches.length) {
      wrap.innerHTML = `<p class="note">No bulk BBPS batches yet.</p>`;
      return;
    }
    wrap.innerHTML = `<table class="desk-table"><thead><tr>
      <th>Batch / Retailer</th><th>File</th><th>Pipe</th><th>Status</th><th class="num">Rows</th><th class="num">Fetch</th><th class="num">Paid</th><th></th>
    </tr></thead><tbody>${batches
      .map((b) => {
        const rid = accountIdForEmail(b.user_id, "retailer");
        return `<tr>
        <td><strong class="mono">${escHtml(b.batch_id)}</strong><small>${escHtml(rid)} · ${escHtml(b.user_id || "")}</small></td>
        <td>${escHtml(b.source_filename || "—")}</td>
        <td>${escHtml(b.pipe || "—")}</td>
        <td><span class="pill">${escHtml(b.status || "")}</span></td>
        <td class="num">${escHtml(String(b.row_count || 0))}</td>
        <td class="num">${escHtml(String(b.fetch_ok || 0))}/${escHtml(String(b.fetch_fail || 0))}</td>
        <td class="num">${escHtml(inr(b.paid_total || 0))}</td>
        <td><button type="button" class="btn-xs" data-bulk-sync="${escHtml(b.batch_id)}">Sync fetch</button></td>
      </tr>`;
      })
      .join("")}</tbody></table>`;
    wrap.querySelectorAll("[data-bulk-sync]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        const sync = await call(`/api/auth/desk/bbps/bulk/${encodeURIComponent(btn.dataset.bulkSync)}`, {
          action: "sync",
        });
        if (!sync.ok) notify(sync.data.error || "Sync failed.");
        else notify(`Synced ${btn.dataset.bulkSync}: fetched ${sync.data.fetched || 0}`);
        loadBulkDesk();
      });
    });
  }

  let moneyFilter = "all";
  let moneyQuery = "";
  let moneyCache = { ledger: [], api: [] };

  function paintMoneyLedger() {
    const moneyList = document.querySelector("[data-money]");
    if (!moneyList) return;
    const ledgerRows = moneyCache.ledger || [];
    const apiRows = moneyCache.api || [];
    const totalEl = document.querySelector("[data-money-total]");
    const okEl = document.querySelector("[data-money-success]");
    const revEl = document.querySelector("[data-money-review]");
    if (totalEl) totalEl.textContent = String(ledgerRows.length + apiRows.length);
    if (okEl) okEl.textContent = String(ledgerRows.length + apiRows.filter((r) => r.outcome === "ok" || r.outcome === "created").length);
    if (revEl) revEl.textContent = String(apiRows.filter((r) => r.outcome === "error" || r.outcome === "conflict").length);

    const q = moneyQuery.trim().toLowerCase();
    const matchQ = (hay) => !q || String(hay || "").toLowerCase().includes(q);

    moneyList.replaceChildren();
    const showLedger = moneyFilter === "all" || moneyFilter === "payswap";
    const showApi = moneyFilter === "all" || moneyFilter === "review" || moneyFilter === "payswap";
    const filteredApi = (moneyFilter === "review"
      ? apiRows.filter((r) => r.outcome === "error" || r.outcome === "conflict")
      : moneyFilter === "payswap"
      ? apiRows.filter((r) => r.app_context === "payswap")
      : apiRows
    ).filter((r) => matchQ([r.action, r.actor, r.target_id, r.idempotency_key].join(" ")));

    const visibleLedger = (showLedger && moneyFilter !== "review" ? ledgerRows : [])
      .filter((l) => matchQ([l.entry_type, l.user_id, l.reference, l.narration, l.entry_id].join(" ")));

    if (!visibleLedger.length && (!showApi || !filteredApi.length)) {
      const empty = document.createElement("div");
      empty.className = "log-empty";
      empty.textContent = q
        ? "No wallet ledger entries or API money writes match your search."
        : "No wallet ledger entries or API money writes match this filter.";
      moneyList.appendChild(empty);
      return;
    }
    visibleLedger.forEach((l) => {
      const row = document.createElement("div");
      row.className = "ledger-row";
      const dirKind = l.direction === "CR" ? "success" : "pending";
      row.innerHTML = `<span><strong>${escHtml(l.entry_type)}</strong><small>${escHtml(l.narration || "—")} · ${escHtml(logTime(l.created_at))}</small></span><span>${escHtml(l.user_id)}<small>${escHtml(l.actor || "")}</small></span><span><span class="pill ${dirKind}">${escHtml(l.direction)} ${inr(l.amount)}</span></span><span class="mono">${escHtml(l.reference || l.entry_id)}</span><span><span class="pill success">Bal ${inr(l.balance_after)}</span></span>`;
      moneyList.appendChild(row);
    });
    if (showApi) {
      filteredApi.forEach((r) => {
        const row = document.createElement("div");
        row.className = "ledger-row";
        const kind = r.outcome === "error" ? "failed" : r.outcome === "conflict" ? "pending" : "success";
        row.innerHTML = `<span><strong>${escHtml(r.action)}</strong><small>${escHtml(logTime(r.at))}</small></span><span>${escHtml(r.actor || "—")}</span><span>${escHtml((r.app_context || "—").toUpperCase())}</span><span class="mono">${escHtml(r.target_id || r.idempotency_key || "—")}</span><span><span class="pill ${kind}">${escHtml(r.outcome)} (${escHtml(r.status)})</span></span>`;
        moneyList.appendChild(row);
      });
    }
  }

  async function loadMoney() {
    if (!peopleRows.length) await loadPeople();
    const walletsRes = await call("/api/auth/desk/wallets");

    const topupsWrap = document.querySelector("[data-desk-topups]");
    if (topupsWrap) {
      const reqs = walletsRes.ok ? (walletsRes.data.topup_requests || []) : [];
      const pendingBadge = document.querySelector("[data-fund-pending-count]");
      if (pendingBadge) pendingBadge.textContent = String(reqs.filter((r) => r.status === "pending").length);
      if (!reqs.length) {
        topupsWrap.innerHTML = `<p class="note">${walletsRes.ok ? "No UTR top-up requests yet." : escHtml(walletsRes.data.error || "Could not load top-ups.")}</p>`;
      } else {
        const html = reqs
          .slice(0, 15)
          .map((t) => {
            const actions = t.status === "pending"
              ? `<button type="button" class="btn-xs primary" data-topup-act="approve" data-topup-id="${escHtml(t.request_id)}">Approve</button>
                 <button type="button" class="btn-xs danger" data-topup-act="reject" data-topup-id="${escHtml(t.request_id)}">Reject</button>`
              : `<small>${escHtml(t.reviewed_by || "—")}</small>`;
            return `<tr>
              <td><strong>${escHtml(t.user_id)}</strong><br><small>UTR: ${escHtml(t.utr)} · ${escHtml(t.mode)} · ${escHtml(fullDateTime(t.created_at))}</small></td>
              <td class="num"><strong>${inr(t.amount)}</strong></td>
              <td><span class="pill ${t.status === "approved" ? "success" : t.status === "pending" ? "pending" : "failed"}">${escHtml(t.status)}</span></td>
              <td><div class="desk-actions"><button type="button" class="btn-xs" data-topup-open-fund="${escHtml(t.request_id)}">Details</button>${actions}</div></td>
            </tr>`;
          })
          .join("");
        topupsWrap.innerHTML = `<table class="desk-table"><thead><tr><th>Retailer / UTR</th><th class="num">Amount</th><th>Status</th><th style="text-align:right">Action</th></tr></thead><tbody>${html}</tbody></table>`;
        topupsWrap.querySelectorAll("[data-topup-open-fund]").forEach((btn) => {
          btn.addEventListener("click", () => {
            fundSelectedId = btn.dataset.topupOpenFund || "";
            room("fund-requests");
          });
        });
        topupsWrap.querySelectorAll("[data-topup-act]").forEach((btn) => {
          btn.addEventListener("click", async () => {
            const act = btn.dataset.topupAct;
            const request_id = btn.dataset.topupId;
            const note = act === "reject" ? (window.prompt("Reason for rejection:", "UTR not matched in bank statement") || "Rejected") : "Verified in bank statement";
            btn.disabled = true;
            const res = await call("/api/auth/desk/wallets/topup-review", { request_id, decision: act, note });
            if (!res.ok) notify(res.data.error || "Action failed.");
            else notify(`Top-up ${act}d.`);
            loadMoney();
          });
        });
      }
    }

    const walletsWrap = document.querySelector("[data-desk-wallets]");
    if (walletsWrap) {
      const rows = walletsRes.ok ? (walletsRes.data.wallets || []) : [];
      if (!rows.length) {
        walletsWrap.innerHTML = `<p class="note">No retailer wallets initialized yet.</p>`;
      } else {
        const html = rows
          .map((w) => {
            const isFrozen = w.status === "frozen";
            return `<tr>
              <td><strong>${escHtml(w.user_id)}</strong><br><small>Daily used: ${inr(w.daily_used)} / ${inr(w.daily_debit_limit)} · PIN: ${w.has_pin ? "Set" : "Not set"}</small></td>
              <td class="num"><strong>${inr(w.available)}</strong></td>
              <td class="num">${inr(w.held)}</td>
              <td><span class="pill ${isFrozen ? "failed" : "success"}">${isFrozen ? "Frozen" : "Active"}</span></td>
              <td>
                <div class="desk-actions">
                  <button type="button" class="btn-xs" data-wallet-prefill="${escHtml(w.user_id)}">Adjust</button>
                  <button type="button" class="btn-xs" data-wallet-reset-pin="${escHtml(w.user_id)}">Reset PIN</button>
                  <button type="button" class="btn-xs ${isFrozen ? "primary" : "danger"}" data-wallet-freeze="${escHtml(w.user_id)}" data-frozen="${isFrozen ? "1" : "0"}">${isFrozen ? "Unfreeze" : "Freeze"}</button>
                </div>
              </td>
            </tr>`;
          })
          .join("");
        walletsWrap.innerHTML = `<table class="desk-table"><thead><tr><th>Retailer</th><th class="num">Available</th><th class="num">Held</th><th>Status</th><th style="text-align:right">Controls</th></tr></thead><tbody>${html}</tbody></table>`;
        walletsWrap.querySelectorAll("[data-wallet-prefill]").forEach((btn) => {
          btn.addEventListener("click", () => {
            const form = document.getElementById("admin-wallet-adjust");
            if (!form) return;
            form.elements.email.value = btn.dataset.walletPrefill;
            form.scrollIntoView({ behavior: "smooth", block: "center" });
            form.elements.amount?.focus();
          });
        });
        walletsWrap.querySelectorAll("[data-wallet-reset-pin]").forEach((btn) => {
          btn.addEventListener("click", async () => {
            const email = btn.dataset.walletResetPin;
            const res = await call("/api/auth/desk/wallets/controls", { email, reset_pin: true });
            if (!res.ok) notify(res.data.error || "Could not reset PIN.");
            else notify(`PIN cleared for ${email}.`);
            loadMoney();
          });
        });
        walletsWrap.querySelectorAll("[data-wallet-freeze]").forEach((btn) => {
          btn.addEventListener("click", async () => {
            const email = btn.dataset.walletFreeze;
            const isFrozen = btn.dataset.frozen === "1";
            const reason = isFrozen ? "" : (window.prompt("Freeze reason:", "Admin review") || "Admin freeze");
            const res = await call("/api/auth/desk/wallets/controls", {
              email,
              status: isFrozen ? "active" : "frozen",
              freeze_reason: reason,
            });
            if (!res.ok) notify(res.data.error || "Could not update freeze status.");
            else notify(isFrozen ? "Wallet unfrozen." : "Wallet frozen.");
            loadMoney();
          });
        });
      }
    }

    moneyCache = {
      ledger: walletsRes.ok ? (walletsRes.data.ledger || []) : [],
      api: [],
    };
    paintMoneyLedger();
  }

  let fundTab = "all";
  let fundMode = "all";
  let fundQuery = "";
  let fundSelectedId = "";
  let fundCache = { topups: [], pgTopups: [] };

  function fullDateTime(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function appendFact(dl, label, value, mono = false) {
    if (value === undefined || value === null || value === "") return;
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = String(value);
    if (mono) dd.className = "log-exchange";
    dl.append(dt, dd);
  }

  function showFundDetail(row, kind) {
    const panel = document.querySelector("[data-fund-detail]");
    if (!panel || !row) return;
    const id = kind === "pg" ? row.pg_order_id : row.request_id;
    fundSelectedId = id || "";
    panel.hidden = false;

    const idEl = panel.querySelector("[data-fund-detail-id]");
    const titleEl = panel.querySelector("[data-fund-detail-title]");
    const subEl = panel.querySelector("[data-fund-detail-sub]");
    const statusEl = panel.querySelector("[data-fund-detail-status]");
    const facts = panel.querySelector("[data-fund-detail-facts]");
    const reviewForm = document.getElementById("fund-detail-review-form");

    if (kind === "pg") {
      if (idEl) idEl.textContent = row.pg_order_id || "PG Top-up";
      if (titleEl) titleEl.textContent = `${row.user_id} · ${inr(row.amount)}`;
      if (subEl) subEl.textContent = `Cashfree Payment Gateway wallet load (${row.provider || "cashfree"})`;
      if (statusEl) {
        statusEl.textContent = row.status || "created";
        statusEl.className = "pill " + (row.status === "paid" ? "success" : row.status === "created" ? "pending" : "failed");
      }
      if (facts) {
        facts.replaceChildren();
        appendFact(facts, "PG Order ID", row.pg_order_id, true);
        appendFact(facts, "Retailer Email", row.user_id);
        appendFact(facts, "Amount", inr(row.amount));
        appendFact(facts, "Provider", row.provider || "cashfree");
        appendFact(facts, "Status", row.status);
        appendFact(facts, "Provider Order ID", row.provider_order_id || "—", true);
        appendFact(facts, "Provider Payment ID", row.provider_payment_id || "—", true);
        appendFact(facts, "Signature Verified", row.signature_verified ? "Yes" : "No");
        appendFact(facts, "Paid At", fullDateTime(row.paid_at));
        appendFact(facts, "Created At", fullDateTime(row.created_at));
        appendFact(facts, "Updated At", fullDateTime(row.updated_at));
        if (row.checkout_url) appendFact(facts, "Checkout URL", row.checkout_url, true);
      }
      if (reviewForm) reviewForm.hidden = true;
    } else {
      if (idEl) idEl.textContent = row.request_id || "Fund Request";
      if (titleEl) titleEl.textContent = `${row.user_id} · ${inr(row.amount)}`;
      if (subEl) subEl.textContent = `${row.mode || "BANK_TRANSFER"} · UTR ${row.utr || "—"}`;
      if (statusEl) {
        statusEl.textContent = row.status || "pending";
        statusEl.className = "pill " + (row.status === "approved" ? "success" : row.status === "pending" ? "pending" : "failed");
      }
      if (facts) {
        facts.replaceChildren();
        appendFact(facts, "Request ID", row.request_id, true);
        appendFact(facts, "Retailer Email", row.user_id);
        appendFact(facts, "Amount", `${inr(row.amount)} (${row.amount_paise || 0} paise)`);
        appendFact(facts, "Transfer Mode", row.mode || "—");
        appendFact(facts, "UTR / Bank Ref", row.utr || "—", true);
        appendFact(facts, "Retailer Remarks", row.remarks || "—");
        appendFact(facts, "Submitted At", fullDateTime(row.created_at));
        appendFact(facts, "Status", (row.status || "").toUpperCase());
        appendFact(facts, "Wallet Status", row.wallet_status ? row.wallet_status.toUpperCase() : "—");
        appendFact(facts, "Current Available", row.wallet_available != null ? inr(row.wallet_available) : "—");
        appendFact(facts, "Current Held", row.wallet_held != null ? inr(row.wallet_held) : "—");
        appendFact(facts, "Per-Txn / Daily Limit", row.wallet_per_txn_limit != null ? `${inr(row.wallet_per_txn_limit)} / ${inr(row.wallet_daily_limit)}` : "—");
        appendFact(facts, "Reviewed By", row.reviewed_by || "Pending admin review");
        appendFact(facts, "Reviewed At", row.reviewed_at ? fullDateTime(row.reviewed_at) : "—");
        appendFact(facts, "Review Note", row.review_note || "—");
        if (row.ledger_entry) {
          const le = row.ledger_entry;
          appendFact(facts, "Ledger Entry ID", le.entry_id, true);
          appendFact(facts, "Ledger Type", `${le.direction} · ${le.entry_type}`);
          appendFact(facts, "Balance Transition", `${inr(le.balance_before)} → ${inr(le.balance_after)}`);
          appendFact(facts, "Credited At", fullDateTime(le.created_at));
        }
      }
      if (reviewForm) {
        reviewForm.hidden = row.status !== "pending";
        reviewForm.dataset.requestId = row.request_id || "";
        if (reviewForm.elements.note) reviewForm.elements.note.value = "";
      }
    }
    panel.scrollIntoView({ block: "nearest" });
  }

  function filteredFundRows() {
    const q = fundQuery.trim().toLowerCase();
    const matchQ = (hay) => !q || String(hay || "").toLowerCase().includes(q);
    if (fundTab === "pg") {
      return (fundCache.pgTopups || []).filter((p) =>
        matchQ([p.pg_order_id, p.user_id, p.provider_order_id, p.provider_payment_id, p.status].join(" "))
      );
    }
    return (fundCache.topups || []).filter((t) => {
      if (fundTab !== "all" && t.status !== fundTab) return false;
      if (fundMode !== "all" && t.mode !== fundMode) return false;
      return matchQ([t.request_id, t.user_id, t.utr, t.mode, t.remarks, t.reviewed_by, t.review_note, t.status].join(" "));
    });
  }

  function paintFundRequests() {
    const topups = fundCache.topups || [];
    const pgTopups = fundCache.pgTopups || [];
    const setText = (sel, txt) => {
      const el = document.querySelector(sel);
      if (el) el.textContent = txt;
    };
    const pending = topups.filter((t) => t.status === "pending");
    const approved = topups.filter((t) => t.status === "approved");
    const rejected = topups.filter((t) => t.status === "rejected");
    const paidPg = pgTopups.filter((p) => p.status === "paid");

    const sumAmt = (arr) => arr.reduce((a, x) => a + Number(x.amount || 0), 0);
    setText("[data-fund-pending-count]", String(pending.length));
    setText("[data-fund-pending-badge]", `${pending.length} pending`);
    setText("[data-fund-pending-vol]", inr(sumAmt(pending)));
    setText("[data-fund-approved-badge]", `${approved.length} approved`);
    setText("[data-fund-approved-vol]", inr(sumAmt(approved)));
    setText("[data-fund-rejected-badge]", `${rejected.length} rejected`);
    setText("[data-fund-rejected-vol]", inr(sumAmt(rejected)));
    setText("[data-fund-pg-badge]", `${pgTopups.length} orders (${paidPg.length} paid)`);
    setText("[data-fund-pg-vol]", inr(sumAmt(paidPg)));

    setText('[data-fund-tab-count="all"]', `(${topups.length})`);
    setText('[data-fund-tab-count="pending"]', `(${pending.length})`);
    setText('[data-fund-tab-count="approved"]', `(${approved.length})`);
    setText('[data-fund-tab-count="rejected"]', `(${rejected.length})`);
    setText('[data-fund-tab-count="pg"]', `(${pgTopups.length})`);

    document.querySelectorAll("[data-fund-tab]").forEach((btn) => {
      btn.classList.toggle("is-on", btn.dataset.fundTab === fundTab);
    });

    const rows = filteredFundRows();
    setText("[data-fund-total-count]", `${rows.length} ${fundTab === "pg" ? "orders" : "requests"}`);
    const wrap = document.querySelector("[data-fund-requests-table]");
    if (!wrap) return;

    if (!rows.length) {
      wrap.innerHTML = `<p class="note">${fundQuery ? "No fund requests match your search." : "No fund requests in this view."}</p>`;
      return;
    }

    if (fundTab === "pg") {
      const html = rows
        .map((p) => {
          const picked = p.pg_order_id === fundSelectedId ? "is-picked" : "";
          return `<tr class="${picked}">
            <td><strong class="mono-sm">${escHtml(p.pg_order_id)}</strong><br><small>Created ${escHtml(fullDateTime(p.created_at))}</small>${p.updated_at ? `<br><small>Updated ${escHtml(fullDateTime(p.updated_at))}</small>` : ""}</td>
            <td><strong>${escHtml(p.user_id)}</strong><br><small>${escHtml((p.provider || "cashfree").toUpperCase())} · ${p.signature_verified ? "Sig OK" : "Unverified"}</small></td>
            <td><span class="mono-sm">${escHtml(p.provider_payment_id || p.provider_order_id || "—")}</span></td>
            <td class="num"><strong>${inr(p.amount)}</strong></td>
            <td><span class="pill ${p.status === "paid" ? "success" : p.status === "created" ? "pending" : "failed"}">${escHtml(p.status)}</span><br><small>${p.paid_at ? `Paid ${escHtml(fullDateTime(p.paid_at))}` : "Awaiting payment"}</small></td>
            <td><div class="desk-actions"><button type="button" class="btn-xs" data-fund-inspect-pg="${escHtml(p.pg_order_id)}">Full details</button></div></td>
          </tr>`;
        })
        .join("");
      wrap.innerHTML = `<table class="desk-table"><thead><tr><th>PG Order / Date</th><th>Retailer</th><th>Provider Ref</th><th class="num">Amount</th><th>Status / Paid</th><th style="text-align:right">Actions</th></tr></thead><tbody>${html}</tbody></table>`;
      wrap.querySelectorAll("[data-fund-inspect-pg]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const match = (fundCache.pgTopups || []).find((x) => x.pg_order_id === btn.dataset.fundInspectPg);
          if (match) {
            showFundDetail(match, "pg");
            paintFundRequests();
          }
        });
      });
      return;
    }

    const html = rows
      .map((t) => {
        const picked = t.request_id === fundSelectedId ? "is-picked" : "";
        const audit = t.status === "pending"
          ? `<small>Awaiting verification</small>`
          : `<small>${escHtml(t.reviewed_by || "—")} · ${escHtml(fullDateTime(t.reviewed_at))}</small>${t.review_note ? `<br><small>${escHtml(t.review_note)}</small>` : ""}`;
        const walletSnap = t.wallet_available != null
          ? `<small>Wallet: ${inr(t.wallet_available)} (${escHtml(t.wallet_status || "active")})</small>`
          : "";
        const ledgerSnap = t.ledger_entry
          ? `<br><small class="mono-sm">Bal: ${inr(t.ledger_entry.balance_before)} → ${inr(t.ledger_entry.balance_after)}</small>`
          : "";
        const quickActions = t.status === "pending"
          ? `<button type="button" class="btn-xs primary" data-fund-act="approve" data-fund-id="${escHtml(t.request_id)}">Approve</button>
             <button type="button" class="btn-xs danger" data-fund-act="reject" data-fund-id="${escHtml(t.request_id)}">Reject</button>`
          : "";
        return `<tr class="${picked}">
          <td><strong class="mono-sm">${escHtml(t.request_id)}</strong><br><small>${escHtml(fullDateTime(t.created_at))}</small></td>
          <td><strong>${escHtml(t.user_id)}</strong><br>${walletSnap}</td>
          <td><strong>${escHtml(t.mode)}</strong> · <span class="mono-sm">${escHtml(t.utr)}</span><br><small>${escHtml(t.remarks || "No remarks")}</small></td>
          <td class="num"><strong>${inr(t.amount)}</strong>${ledgerSnap}</td>
          <td><span class="pill ${t.status === "approved" ? "success" : t.status === "pending" ? "pending" : "failed"}">${escHtml(t.status)}</span><br>${audit}</td>
          <td><div class="desk-actions"><button type="button" class="btn-xs" data-fund-inspect="${escHtml(t.request_id)}">Full details</button>${quickActions}</div></td>
        </tr>`;
      })
      .join("");
    wrap.innerHTML = `<table class="desk-table"><thead><tr><th>Request ID / Submitted</th><th>Retailer / Wallet</th><th>Mode / UTR / Remarks</th><th class="num">Amount</th><th>Status / Audit</th><th style="text-align:right">Actions</th></tr></thead><tbody>${html}</tbody></table>`;

    wrap.querySelectorAll("[data-fund-inspect]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const match = (fundCache.topups || []).find((x) => x.request_id === btn.dataset.fundInspect);
        if (match) {
          showFundDetail(match, "utr");
          paintFundRequests();
        }
      });
    });

    wrap.querySelectorAll("[data-fund-act]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const act = btn.dataset.fundAct;
        const request_id = btn.dataset.fundId;
        const note = act === "reject"
          ? (window.prompt("Reason for rejection:", "UTR not matched in bank statement") || "Rejected")
          : "Verified in bank statement";
        btn.disabled = true;
        const res = await call("/api/auth/desk/wallets/topup-review", { request_id, decision: act, note });
        if (!res.ok) notify(res.data.error || "Action failed.");
        else notify(`Fund request ${act}d.`);
        await loadFundRequests();
      });
    });
  }

  async function loadFundRequests() {
    if (!peopleRows.length) await loadPeople();
    const res = await call("/api/auth/desk/wallets");
    if (!res.ok) {
      const wrap = document.querySelector("[data-fund-requests-table]");
      if (wrap) wrap.innerHTML = `<p class="note">${escHtml(res.data.error || "Could not load fund requests.")}</p>`;
      return;
    }
    fundCache = {
      topups: res.data.topup_requests || [],
      pgTopups: res.data.pg_topups || [],
    };
    paintFundRequests();
    if (fundSelectedId) {
      const openUtr = fundCache.topups.find((x) => x.request_id === fundSelectedId);
      const openPg = fundCache.pgTopups.find((x) => x.pg_order_id === fundSelectedId);
      if (openUtr) showFundDetail(openUtr, "utr");
      else if (openPg) showFundDetail(openPg, "pg");
    }
  }

  let reportTab = "bbps";
  let reportSelectedKey = "";
  let reportPage = 0;
  const REPORT_PAGE_SIZE = 25;
  let reportData = { bbps_transactions: [], topup_requests: [], pg_orders: [], ledger: [], holds: [], voucher_orders: [] };
  const REPORT_TAB_META = {
    bbps: { title: "BBPS transactions", hint: "Filter All / Success / Pending / Failed. Use Check status for pending Mobikwik rows." },
    topups: { title: "Fund requests", hint: "Filter by approved, pending, or rejected UTR / bank float submissions." },
    pg: { title: "PG orders", hint: "Filter paid, awaiting, or failed. Stale awaiting orders auto-check and fail after 30 minutes." },
    ledger: { title: "Wallet ledger", hint: "Double-entry credits and debits for retailer float." },
    holds: { title: "Wallet holds", hint: "Filter captured, active, or released holds tied to BBPS or other services." },
    vouchers: { title: "Voucher orders", hint: "Gift voucher purchases recorded through PaySwap." },
  };

  function reportRowsForTab() {
    if (reportTab === "topups") return reportData.topup_requests || [];
    if (reportTab === "pg") return reportData.pg_orders || [];
    if (reportTab === "ledger") return reportData.ledger || [];
    if (reportTab === "holds") return reportData.holds || [];
    if (reportTab === "vouchers") return reportData.voucher_orders || [];
    return reportData.bbps_transactions || [];
  }

  function reportRowKey(row) {
    if (reportTab === "topups") return row.request_id || "";
    if (reportTab === "pg") return row.pg_order_id || "";
    if (reportTab === "ledger") return row.entry_id || "";
    if (reportTab === "holds") return row.hold_id || "";
    return row.reference || "";
  }

  function reportRetailerLabel(email) {
    const rid = accountIdForEmail(email, "retailer");
    if (rid) return `${rid} · ${email || ""}`.trim();
    return email || "—";
  }

  function reportRetailerCell(email) {
    const rid = accountIdForEmail(email, "retailer");
    if (rid) {
      return `<strong class="mono-sm">${escHtml(rid)}</strong><br><small>${escHtml(email || "—")}</small>`;
    }
    return `<span>${escHtml(email || "—")}</span>`;
  }

  function syncReportFilterVisibility() {
    const showStatus = reportTab === "bbps" || reportTab === "pg" || reportTab === "topups" || reportTab === "holds";
    const showRail = reportTab === "bbps";
    document.querySelectorAll(".reports-filter-status").forEach((el) => {
      el.hidden = !showStatus;
    });
    document.querySelectorAll(".reports-filter-bbps").forEach((el) => {
      el.hidden = !showRail;
    });
    const statusLabel = document.querySelector("[data-report-status-label]");
    if (statusLabel) {
      statusLabel.textContent =
        reportTab === "pg"
          ? "PG status"
          : reportTab === "topups"
            ? "Request status"
            : reportTab === "holds"
              ? "Hold status"
              : "BBPS status";
    }
    const meta = REPORT_TAB_META[reportTab] || REPORT_TAB_META.bbps;
    const title = document.querySelector("[data-report-table-title]");
    const hint = document.querySelector("[data-report-table-hint]");
    if (title) title.textContent = meta.title;
    if (hint) hint.textContent = meta.hint;
  }

  function paintReportPagination(total) {
    const control = document.querySelector("[data-report-pagination]");
    if (!control) return;
    const pages = Math.max(1, Math.ceil(total / REPORT_PAGE_SIZE) || 1);
    reportPage = Math.min(Math.max(0, reportPage), pages - 1);
    const start = total ? reportPage * REPORT_PAGE_SIZE + 1 : 0;
    const end = Math.min((reportPage + 1) * REPORT_PAGE_SIZE, total);
    control.replaceChildren();
    if (!total) {
      control.hidden = true;
      return;
    }
    control.hidden = false;
    const count = document.createElement("span");
    count.className = "log-page-count";
    if (total <= REPORT_PAGE_SIZE) {
      count.textContent = `${total} record${total === 1 ? "" : "s"}`;
      control.append(count);
      return;
    }
    count.textContent = `${start}–${end} of ${total} · Page ${reportPage + 1} of ${pages}`;
    const actions = document.createElement("span");
    actions.className = "log-page-actions";
    [
      ["Previous", reportPage - 1, reportPage === 0],
      ["Next", reportPage + 1, reportPage >= pages - 1],
    ].forEach(([label, target, disabled]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "log-page-button";
      button.dataset.reportPage = String(target);
      button.textContent = label;
      button.disabled = disabled;
      actions.append(button);
    });
    control.append(count, actions);
  }

  function bindReportInspect(wrap, rows, kind) {
    wrap.querySelectorAll("[data-rep-inspect]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.repInspect || "";
        const row = rows.find((x) => reportRowKey(x) === key);
        if (row) {
          showReportDetail(row, kind);
          paintReportsTable();
        }
      });
    });
  }

  function showReportDetail(row, kind) {
    const panel = document.querySelector("[data-report-detail]");
    if (!panel || !row) return;
    const idEl = panel.querySelector("[data-report-detail-id]");
    const titleEl = panel.querySelector("[data-report-detail-title]");
    const subEl = panel.querySelector("[data-report-detail-sub]");
    const facts = panel.querySelector("[data-report-detail-facts]");
    const syncBtn = panel.querySelector("[data-report-detail-sync]");

    panel.hidden = false;
    facts.replaceChildren();
    if (syncBtn) {
      const canSync = (kind === "bbps" && row.state === "pending") || (kind === "pg" && row.status === "created");
      syncBtn.hidden = !canSync;
      syncBtn.dataset.reference = kind === "bbps" ? (row.reference || "") : "";
      syncBtn.dataset.pgOrderId = kind === "pg" ? (row.pg_order_id || "") : "";
      syncBtn.textContent = "Check live status";
    }

    if (kind === "bbps") {
      reportSelectedKey = row.reference || "";
      if (idEl) idEl.textContent = row.reference || "BBPS";
      if (titleEl) titleEl.textContent = `${row.biller || row.operator_id} · ${inr(row.amount)}`;
      if (subEl) subEl.textContent = `${reportRetailerLabel(row.user_id)} · ${row.category || "BBPS"} · ${(row.state || "").toUpperCase()}`;
      appendFact(facts, "Reference", row.reference, true);
      appendFact(facts, "Retailer", reportRetailerLabel(row.user_id), true);
      appendFact(facts, "Biller / Operator", `${row.biller || "—"} (${row.operator_id || "—"})`);
      appendFact(facts, "Category", row.category || "—");
      appendFact(facts, "Consumer / Account", row.account || "—", true);
      appendFact(facts, "Amount", `${inr(row.amount)} (${row.amount_paise || 0} paise)`);
      appendFact(facts, "Payment Rail / Mode", `${(row.payment_channel || "").toUpperCase()} · ${row.payment_mode || "—"}`);
      appendFact(facts, "State", (row.state || "").toUpperCase());
      appendFact(facts, "Vendor Status", row.vendor_status || "—");
      appendFact(facts, "Vendor Txn ID", row.vendor_txn_id || "—", true);
      appendFact(facts, "Error / Reason", row.error_message || "—");
      appendFact(facts, "Wallet Hold ID", row.wallet_hold_id ? `${row.wallet_hold_id}${row.hold_status ? " (" + row.hold_status + ")" : ""}` : "—", true);
      appendFact(facts, "PG Order ID", row.pg_order_id || "—", true);
      appendFact(facts, "Idempotency Key", row.idempotency_key || "—", true);
      appendFact(facts, "Last Checked At", fullDateTime(row.last_checked_at));
      appendFact(facts, "Created At", fullDateTime(row.created_at));
      appendFact(facts, "Updated At", fullDateTime(row.updated_at));
    } else if (kind === "topups") {
      reportSelectedKey = row.request_id || "";
      if (idEl) idEl.textContent = row.request_id || "Fund Request";
      if (titleEl) titleEl.textContent = `${reportRetailerLabel(row.user_id)} · ${inr(row.amount)}`;
      if (subEl) subEl.textContent = `${row.mode} · UTR ${row.utr} · ${(row.status || "").toUpperCase()}`;
      appendFact(facts, "Request ID", row.request_id, true);
      appendFact(facts, "Retailer", reportRetailerLabel(row.user_id), true);
      appendFact(facts, "Amount", inr(row.amount));
      appendFact(facts, "Mode", row.mode);
      appendFact(facts, "UTR / Reference", row.utr, true);
      appendFact(facts, "Remarks", row.remarks || "—");
      appendFact(facts, "Status", (row.status || "").toUpperCase());
      appendFact(facts, "Reviewed By", row.reviewed_by || "Pending");
      appendFact(facts, "Reviewed At", fullDateTime(row.reviewed_at));
      appendFact(facts, "Review Note", row.review_note || "—");
      if (row.ledger_entry) {
        appendFact(facts, "Ledger Entry", `${row.ledger_entry.entry_id} (${inr(row.ledger_entry.balance_before)} → ${inr(row.ledger_entry.balance_after)})`, true);
      }
      appendFact(facts, "Created At", fullDateTime(row.created_at));
    } else if (kind === "pg") {
      reportSelectedKey = row.pg_order_id || "";
      if (idEl) idEl.textContent = row.pg_order_id || "PG Order";
      if (titleEl) titleEl.textContent = `${row.purpose} · ${inr(row.amount)}`;
      if (subEl) subEl.textContent = `${reportRetailerLabel(row.user_id)} · ${(row.status || "").toUpperCase()}`;
      appendFact(facts, "PG Order ID", row.pg_order_id, true);
      appendFact(facts, "Retailer", reportRetailerLabel(row.user_id), true);
      appendFact(facts, "Provider", row.provider || "cashfree");
      appendFact(facts, "Purpose", row.purpose);
      appendFact(facts, "Service Reference", row.service_ref || "—", true);
      appendFact(facts, "Amount", `${inr(row.amount)} (${row.currency || "INR"})`);
      appendFact(facts, "Status", (row.status || "").toUpperCase());
      appendFact(facts, "Provider Order ID", row.provider_order_id || "—", true);
      appendFact(facts, "Provider Payment ID", row.provider_payment_id || "—", true);
      appendFact(facts, "Signature Verified", row.signature_verified ? "Yes" : "No");
      appendFact(facts, "Paid At", fullDateTime(row.paid_at));
      appendFact(facts, "Created At", fullDateTime(row.created_at));
      appendFact(facts, "Updated At", fullDateTime(row.updated_at));
      if (row.meta && Object.keys(row.meta).length) appendFact(facts, "Metadata", JSON.stringify(row.meta, null, 2), true);
    } else if (kind === "ledger") {
      reportSelectedKey = row.entry_id || "";
      if (idEl) idEl.textContent = row.entry_id || "Ledger Entry";
      if (titleEl) titleEl.textContent = `${row.entry_type} · ${row.direction} ${inr(row.amount)}`;
      if (subEl) subEl.textContent = `${reportRetailerLabel(row.user_id)} · ${row.narration || "—"}`;
      appendFact(facts, "Entry ID", row.entry_id, true);
      appendFact(facts, "Retailer", reportRetailerLabel(row.user_id), true);
      appendFact(facts, "Direction / Type", `${row.direction} · ${row.entry_type}`);
      appendFact(facts, "Amount", inr(row.amount));
      appendFact(facts, "Available Balance", `${inr(row.balance_before)} → ${inr(row.balance_after)}`);
      appendFact(facts, "Held Balance", `${inr(row.held_before)} → ${inr(row.held_after)}`);
      appendFact(facts, "Reference", row.reference || "—", true);
      appendFact(facts, "Actor / Role", `${row.actor || "—"} (${row.actor_role || "—"})`);
      appendFact(facts, "Idempotency Key", row.idempotency_key || "—", true);
      appendFact(facts, "Narration", row.narration || "—");
      appendFact(facts, "Created At", fullDateTime(row.created_at));
      if (row.meta && Object.keys(row.meta).length) appendFact(facts, "Metadata", JSON.stringify(row.meta, null, 2), true);
    } else if (kind === "holds") {
      reportSelectedKey = row.hold_id || "";
      if (idEl) idEl.textContent = row.hold_id || "Wallet Hold";
      if (titleEl) titleEl.textContent = `${row.service} · ${inr(row.total)}`;
      if (subEl) subEl.textContent = `${reportRetailerLabel(row.user_id)} · ${(row.status || "").toUpperCase()}`;
      appendFact(facts, "Hold ID", row.hold_id, true);
      appendFact(facts, "Retailer", reportRetailerLabel(row.user_id), true);
      appendFact(facts, "Reference", row.reference, true);
      appendFact(facts, "Service", row.service);
      appendFact(facts, "Amount / Fee / Total", `${inr(row.amount)} + ${inr(row.fee)} = ${inr(row.total)}`);
      appendFact(facts, "Status", (row.status || "").toUpperCase());
      appendFact(facts, "Expires At", fullDateTime(row.expires_at));
      appendFact(facts, "Resolved At", fullDateTime(row.resolved_at));
      appendFact(facts, "Created At", fullDateTime(row.created_at));
    } else if (kind === "vouchers") {
      reportSelectedKey = row.reference || "";
      if (idEl) idEl.textContent = row.reference || "Voucher Order";
      if (titleEl) titleEl.textContent = `${row.brand || "Voucher"} · ${inr(row.amount)}`;
      if (subEl) subEl.textContent = `${reportRetailerLabel(row.user_id)} · ${(row.state || "").toUpperCase()}`;
      appendFact(facts, "Reference", row.reference, true);
      appendFact(facts, "Retailer", reportRetailerLabel(row.user_id), true);
      appendFact(facts, "Brand", row.brand || "—");
      appendFact(facts, "Amount", inr(row.amount));
      appendFact(facts, "State", row.state || "—");
      appendFact(facts, "HTTP Status", row.status_code || "—");
      appendFact(facts, "Idempotency Key", row.idempotency_key || "—", true);
      appendFact(facts, "Created At", fullDateTime(row.created_at));
    }
    panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function paintReportsTable() {
    const wrap = document.querySelector("[data-report-table]");
    if (!wrap) return;
    const bbps = reportData.bbps_transactions || [];
    const topups = reportData.topup_requests || [];
    const pg = reportData.pg_orders || [];
    const ledger = reportData.ledger || [];
    const holds = reportData.holds || [];
    const vouchers = reportData.voucher_orders || [];
    const allRows = reportRowsForTab();

    const setText = (sel, txt) => {
      const el = document.querySelector(sel);
      if (el) el.textContent = txt;
    };
    const bbpsSum = bbps.filter((r) => r.state === "success").reduce((a, r) => a + Number(r.amount || 0), 0);
    setText("[data-rep-bbps-vol]", inr(bbpsSum));
    setText(
      "[data-rep-bbps-counts]",
      `${bbps.length} txns · ${bbps.filter((r) => r.state === "pending").length} pending · ${bbps.filter((r) => r.state === "failed").length} failed`,
    );
    const pgSum = pg.filter((r) => r.status === "paid").reduce((a, r) => a + Number(r.amount || 0), 0);
    setText("[data-rep-pg-vol]", inr(pgSum));
    setText("[data-rep-pg-counts]", `${pg.length} orders · ${pg.filter((r) => r.status === "paid").length} paid`);
    const movesAvailable = (row) => !(row.entry_type === "HOLD_CAPTURE" && row.balance_before === row.balance_after);
    const crSum = ledger.filter((r) => r.direction === "CR" && movesAvailable(r)).reduce((a, r) => a + Number(r.amount || 0), 0);
    const drSum = ledger.filter((r) => r.direction === "DR" && movesAvailable(r)).reduce((a, r) => a + Number(r.amount || 0), 0);
    setText("[data-rep-ledger-count]", String(ledger.length));
    setText("[data-rep-ledger-vol]", `CR ${inr(crSum)} · DR ${inr(drSum)}`);
    setText('[data-rep-tab-count="bbps"]', String(bbps.length));
    setText('[data-rep-tab-count="topups"]', String(topups.length));
    setText('[data-rep-tab-count="pg"]', String(pg.length));
    setText('[data-rep-tab-count="ledger"]', String(ledger.length));
    setText('[data-rep-tab-count="holds"]', String(holds.length));
    setText('[data-rep-tab-count="vouchers"]', String(vouchers.length));

    document.querySelectorAll("[data-report-tab]").forEach((btn) => {
      const on = btn.dataset.reportTab === reportTab;
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    syncReportFilterVisibility();
    paintReportPagination(allRows.length);

    if (!allRows.length) {
      const label = (REPORT_TAB_META[reportTab] || {}).title || "records";
      wrap.innerHTML = `<div class="empty-state reports-empty"><strong>No ${escHtml(label.toLowerCase())}</strong><p>Try another tab, clear filters, or widen the search.</p></div>`;
      return;
    }

    const pageRows = allRows.slice(reportPage * REPORT_PAGE_SIZE, (reportPage + 1) * REPORT_PAGE_SIZE);

    if (reportTab === "bbps") {
      const rowsHtml = pageRows
        .map((r) => {
          const picked = r.reference === reportSelectedKey ? "is-picked" : "";
          const syncBtn =
            r.state === "pending"
              ? `<button type="button" class="btn-xs" data-rep-sync="${escHtml(r.reference)}">Check status</button>`
              : "";
          const detail = r.error_message
            ? `<br><small class="is-danger">${escHtml(r.error_message)}</small>`
            : r.vendor_txn_id
              ? `<br><small>Vendor ${escHtml(r.vendor_txn_id)}</small>`
              : "";
          return `<tr class="${picked}">
            <td><strong class="mono-sm">${escHtml(r.reference)}</strong><br><small>${escHtml(fullDateTime(r.created_at))}</small></td>
            <td>${reportRetailerCell(r.user_id)}</td>
            <td>${escHtml(r.biller || r.operator_id)}<br><small>${escHtml(r.account || "—")} · ${escHtml(r.category || "BBPS")}</small></td>
            <td>${escHtml((r.payment_channel || "").toUpperCase())} · ${escHtml(r.payment_mode || "—")}${r.source === "bulk" ? " · bulk" : ""}<br><small class="mono-sm">${escHtml(r.bulk_batch_id || r.wallet_hold_id || r.pg_order_id || "—")}</small></td>
            <td class="num"><strong>${inr(r.amount)}</strong></td>
            <td><span class="pill ${r.state === "success" ? "success" : r.state === "pending" ? "pending" : "failed"}">${escHtml(r.state)}</span>${detail}</td>
            <td class="actions-cell"><div class="desk-actions"><button type="button" class="btn-xs primary" data-rep-inspect="${escHtml(r.reference)}">Open</button>${syncBtn}</div></td>
          </tr>`;
        })
        .join("");
      wrap.innerHTML = `<table class="desk-table"><thead><tr><th>Reference</th><th>Retailer</th><th>Biller / consumer</th><th>Rail</th><th class="num">Amount</th><th>Status</th><th class="actions-cell">Actions</th></tr></thead><tbody>${rowsHtml}</tbody></table>`;
      bindReportInspect(wrap, bbps, "bbps");
      wrap.querySelectorAll("[data-rep-sync]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          const res = await call("/api/auth/desk/transactions/bbps-sync", { reference: btn.dataset.repSync });
          if (!res.ok) notify(res.data.error || "Could not sync status.");
          else notify(`BBPS ${btn.dataset.repSync}: ${res.data.state || "synced"}`);
          await loadReports();
        });
      });
      return;
    }

    if (reportTab === "topups") {
      const rowsHtml = pageRows
        .map((t) => {
          const picked = t.request_id === reportSelectedKey ? "is-picked" : "";
          return `<tr class="${picked}">
            <td><strong class="mono-sm">${escHtml(t.request_id)}</strong><br><small>${escHtml(fullDateTime(t.created_at))}</small></td>
            <td>${reportRetailerCell(t.user_id)}</td>
            <td>${escHtml(t.mode)} · <span class="mono-sm">${escHtml(t.utr)}</span><br><small>${escHtml(t.remarks || "—")}</small></td>
            <td class="num"><strong>${inr(t.amount)}</strong></td>
            <td><span class="pill ${t.status === "approved" ? "success" : t.status === "pending" ? "pending" : "failed"}">${escHtml(t.status)}</span><br><small>${escHtml(t.reviewed_by || "Awaiting review")}</small></td>
            <td class="actions-cell"><div class="desk-actions"><button type="button" class="btn-xs primary" data-rep-inspect="${escHtml(t.request_id)}">Open</button></div></td>
          </tr>`;
        })
        .join("");
      wrap.innerHTML = `<table class="desk-table"><thead><tr><th>Request</th><th>Retailer</th><th>Mode / UTR</th><th class="num">Amount</th><th>Status</th><th class="actions-cell">Actions</th></tr></thead><tbody>${rowsHtml}</tbody></table>`;
      bindReportInspect(wrap, topups, "topups");
      return;
    }

    if (reportTab === "pg") {
      const rowsHtml = pageRows
        .map((p) => {
          const picked = p.pg_order_id === reportSelectedKey ? "is-picked" : "";
          const syncBtn =
            p.status === "created"
              ? `<button type="button" class="btn-xs" data-rep-pg-sync="${escHtml(p.pg_order_id)}">Check status</button>`
              : "";
          const statusNote = p.paid_at
            ? `Paid ${escHtml(fullDateTime(p.paid_at))}`
            : p.status === "failed"
              ? escHtml((p.meta && p.meta.abandon_reason) || "Not completed")
              : "Awaiting payment";
          return `<tr class="${picked}">
            <td><strong class="mono-sm">${escHtml(p.pg_order_id)}</strong><br><small>Created ${escHtml(fullDateTime(p.created_at))}</small>${p.updated_at ? `<br><small>Updated ${escHtml(fullDateTime(p.updated_at))}</small>` : ""}</td>
            <td>${reportRetailerCell(p.user_id)}<br><small>${escHtml((p.provider || "cashfree").toUpperCase())}</small></td>
            <td>${escHtml(p.purpose)}<br><small class="mono-sm">${escHtml(p.service_ref || "—")}</small></td>
            <td class="mono-sm">${escHtml(p.provider_payment_id || p.provider_order_id || "—")}</td>
            <td class="num"><strong>${inr(p.amount)}</strong></td>
            <td><span class="pill ${p.status === "paid" ? "success" : p.status === "created" ? "pending" : "failed"}">${escHtml(p.status)}</span><br><small>${statusNote}</small></td>
            <td class="actions-cell"><div class="desk-actions"><button type="button" class="btn-xs primary" data-rep-inspect="${escHtml(p.pg_order_id)}">Open</button>${syncBtn}</div></td>
          </tr>`;
        })
        .join("");
      wrap.innerHTML = `<table class="desk-table"><thead><tr><th>PG order</th><th>Retailer</th><th>Purpose</th><th>Provider ref</th><th class="num">Amount</th><th>Status</th><th class="actions-cell">Actions</th></tr></thead><tbody>${rowsHtml}</tbody></table>`;
      bindReportInspect(wrap, pg, "pg");
      wrap.querySelectorAll("[data-rep-pg-sync]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          const res = await call("/api/auth/desk/transactions/pg-sync", { pg_order_id: btn.dataset.repPgSync });
          if (!res.ok) notify(res.data.error || "Could not sync PG status.");
          else notify(`PG ${btn.dataset.repPgSync}: ${res.data.status || "synced"}`);
          await loadReports();
        });
      });
      return;
    }

    if (reportTab === "holds") {
      const rowsHtml = pageRows
        .map((h) => {
          const picked = h.hold_id === reportSelectedKey ? "is-picked" : "";
          return `<tr class="${picked}">
            <td><strong class="mono-sm">${escHtml(h.hold_id)}</strong><br><small>${escHtml(fullDateTime(h.created_at))}</small></td>
            <td>${reportRetailerCell(h.user_id)}</td>
            <td>${escHtml((h.service || "").toUpperCase())}<br><small class="mono-sm">${escHtml(h.reference)}</small></td>
            <td class="num"><strong>${inr(h.total)}</strong><br><small>Amt ${inr(h.amount)} + fee ${inr(h.fee)}</small></td>
            <td><span class="pill ${h.status === "captured" ? "success" : h.status === "active" ? "pending" : "neutral"}">${escHtml(h.status)}</span><br><small>${h.resolved_at ? escHtml(fullDateTime(h.resolved_at)) : "Open"}</small></td>
            <td class="actions-cell"><div class="desk-actions"><button type="button" class="btn-xs primary" data-rep-inspect="${escHtml(h.hold_id)}">Open</button></div></td>
          </tr>`;
        })
        .join("");
      wrap.innerHTML = `<table class="desk-table"><thead><tr><th>Hold</th><th>Retailer</th><th>Service / ref</th><th class="num">Total</th><th>Status</th><th class="actions-cell">Actions</th></tr></thead><tbody>${rowsHtml}</tbody></table>`;
      bindReportInspect(wrap, holds, "holds");
      return;
    }

    if (reportTab === "vouchers") {
      const rowsHtml = pageRows
        .map((v) => {
          const picked = v.reference === reportSelectedKey ? "is-picked" : "";
          return `<tr class="${picked}">
            <td><strong class="mono-sm">${escHtml(v.reference)}</strong><br><small>${escHtml(fullDateTime(v.created_at))}</small></td>
            <td>${reportRetailerCell(v.user_id)}</td>
            <td>${escHtml(v.brand || "Voucher")}</td>
            <td class="num"><strong>${inr(v.amount)}</strong></td>
            <td><span class="pill success">${escHtml(v.state || "done")}</span></td>
            <td class="actions-cell"><div class="desk-actions"><button type="button" class="btn-xs primary" data-rep-inspect="${escHtml(v.reference)}">Open</button></div></td>
          </tr>`;
        })
        .join("");
      wrap.innerHTML = `<table class="desk-table"><thead><tr><th>Reference</th><th>Retailer</th><th>Brand</th><th class="num">Amount</th><th>State</th><th class="actions-cell">Actions</th></tr></thead><tbody>${rowsHtml}</tbody></table>`;
      bindReportInspect(wrap, vouchers, "vouchers");
      return;
    }

    const rowsHtml = pageRows
      .map((l) => {
        const picked = l.entry_id === reportSelectedKey ? "is-picked" : "";
        const settledHold = l.entry_type === "HOLD_CAPTURE" && l.balance_before === l.balance_after;
        const amountLabel = settledHold ? "SETTLED ₹0.00" : `${l.direction} ${inr(l.amount)}`;
        return `<tr class="${picked}">
          <td><strong class="mono-sm">${escHtml(l.entry_id)}</strong><br><small>${escHtml(fullDateTime(l.created_at))}</small></td>
          <td>${reportRetailerCell(l.user_id)}<br><small>${escHtml(l.actor || "")}</small></td>
          <td><strong>${escHtml(settledHold ? "HOLD_SETTLED" : l.entry_type)}</strong><br><small>${escHtml(l.narration || "—")}</small></td>
          <td class="mono-sm">${escHtml(l.reference || "—")}</td>
          <td class="num"><span class="pill ${l.direction === "CR" ? "success" : settledHold ? "neutral" : "pending"}">${escHtml(amountLabel)}</span></td>
          <td class="num"><small>${inr(l.balance_before)} →</small> <strong>${inr(l.balance_after)}</strong></td>
          <td class="actions-cell"><div class="desk-actions"><button type="button" class="btn-xs primary" data-rep-inspect="${escHtml(l.entry_id)}">Open</button></div></td>
        </tr>`;
      })
      .join("");
    wrap.innerHTML = `<table class="desk-table"><thead><tr><th>Entry</th><th>Retailer</th><th>Type</th><th>Reference</th><th class="num">Amount</th><th class="num">Balance</th><th class="actions-cell">Actions</th></tr></thead><tbody>${rowsHtml}</tbody></table>`;
    bindReportInspect(wrap, ledger, "ledger");
  }

  async function loadReports() {
    const form = document.getElementById("report-filter-form");
    const statusEl = document.querySelector("[data-report-load-status]");
    const wrap = document.querySelector("[data-report-table]");
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = "Loading…";
    }
    const params = new URLSearchParams();
    const email = form?.elements.email?.value.trim() || "";
    const q = form?.elements.q?.value.trim() || "";
    const state = form?.elements.state?.value || "all";
    const channel = form?.elements.channel?.value || "all";
    const source = form?.elements.source?.value || "all";
    const batchId = form?.elements.batch_id?.value.trim() || "";
    if (email) params.set("email", email);
    if (q) params.set("q", q);
    /* state/channel/source only affect BBPS rows server-side; keep them on every load so tab switches stay consistent. */
    if (state !== "all") params.set("state", state);
    if (channel !== "all") params.set("channel", channel);
    if (source !== "all") params.set("source", source);
    if (batchId) params.set("batch_id", batchId);
    const qs = params.toString();
    const res = await call("/api/auth/desk/transactions" + (qs ? "?" + qs : ""));
    if (statusEl) statusEl.hidden = true;
    if (!res.ok) {
      if (wrap) wrap.innerHTML = `<p class="note empty-state">${escHtml(res.data.error || "Could not load transaction reports.")}</p>`;
      paintReportPagination(0);
      return;
    }
    reportData = {
      bbps_transactions: res.data.bbps_transactions || [],
      topup_requests: res.data.topup_requests || [],
      pg_orders: res.data.pg_orders || [],
      ledger: res.data.ledger || [],
      holds: res.data.holds || [],
      voucher_orders: res.data.voucher_orders || [],
    };
    paintReportsTable();
    if (reportSelectedKey) {
      const activeList = reportRowsForTab();
      const match = (activeList || []).find((x) => reportRowKey(x) === reportSelectedKey);
      if (match) showReportDetail(match, reportTab);
    }
  }

  let logRows = { actions: [], api: [] };
  let logActionService = "all";
  let logApiService = "all";
  const LOG_PAGE_SIZE = 20;
  const logPages = { actions: 0, api: 0 };
  let logOpen = "";

  function logTime(value) {
    const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function resultLabel(outcome) {
    if (outcome === "error") return "Failed";
    if (outcome === "conflict") return "Conflict";
    if (outcome === "replay") return "Replayed";
    if (outcome === "created") return "Created";
    if (outcome === "ok") return "Success";
    return outcome || "Unknown";
  }

  function resultPill(outcome) {
    const pill = document.createElement("span");
    const kind = outcome === "error" ? "failed" : outcome === "conflict" ? "pending" : "success";
    pill.className = "pill " + kind;
    pill.textContent = resultLabel(outcome);
    return pill;
  }

  function emptyLog(list, message) {
    list.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "log-empty";
    empty.textContent = message;
    list.appendChild(empty);
  }

  function logCard(row, kind) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "log-row" + (row.id === logOpen ? " is-picked" : "");
    item.dataset.logOpen = row.id;
    item.dataset.logKind = kind;

    const main = document.createElement("span");
    main.className = "log-row-main";
    const heading = document.createElement("span");
    heading.className = "log-row-heading";
    const id = document.createElement("span");
    id.className = "log-row-id";
    id.textContent = row.id || "Log";
    const title = document.createElement("strong");
    title.className = "log-row-title";
    title.textContent = row.action || eventLabel(row.event);
    heading.append(id, title);
    const summary = document.createElement("span");
    summary.className = "log-row-summary";
    summary.textContent = row.why || "Recorded activity.";
    const metadata = document.createElement("span");
    metadata.className = "log-row-meta";
    const details = kind === "actions"
      ? [row.service, row.email, logTime(row.at)]
      : [row.service, [row.actor, row.role].filter(Boolean).join(" · "), logTime(row.at)];
    details.filter(Boolean).forEach((value) => {
      const part = document.createElement("span");
      part.textContent = value;
      metadata.append(part);
    });
    main.append(heading, summary, metadata);

    const side = document.createElement("span");
    side.className = "log-row-side";
    side.append(resultPill(row.outcome));
    const facts = document.createElement("span");
    facts.className = "log-row-facts";
    const status = row.status === 0 || row.status ? String(row.status) : "";
    const duration = row.duration_ms || row.duration_ms === 0 ? row.duration_ms + " ms" : "";
    facts.textContent = [status, duration].filter(Boolean).join(" · ");
    if (facts.textContent) side.append(facts);
    const hint = document.createElement("span");
    hint.className = "log-row-open";
    hint.textContent = "View details →";
    side.append(hint);
    item.append(main, side);
    return item;
  }

  function logQuote(row) {
    const lines = [
      "Log " + (row.id || ""),
      [row.service, row.action || eventLabel(row.event)].filter(Boolean).join(" · "),
      [resultLabel(row.outcome), row.status].filter((part) => part !== "" && part !== undefined && part !== null).join(" · "),
      row.why || "",
      row.request ? "Request\n" + row.request : "",
      row.response ? "Response\n" + row.response : "",
    ];
    return lines.filter(Boolean).join("\n");
  }

  function paintLogPagination(kind, total) {
    const control = document.querySelector('[data-log-pagination="' + kind + '"]');
    if (!control) return;
    const pages = Math.max(1, Math.ceil(total / LOG_PAGE_SIZE));
    logPages[kind] = Math.min(logPages[kind], pages - 1);
    const page = logPages[kind];
    const start = total ? page * LOG_PAGE_SIZE + 1 : 0;
    const end = Math.min((page + 1) * LOG_PAGE_SIZE, total);
    control.replaceChildren();
    if (total <= LOG_PAGE_SIZE) return;
    const count = document.createElement("span");
    count.className = "log-page-count";
    count.textContent = start + "–" + end + " of " + total;
    const actions = document.createElement("span");
    actions.className = "log-page-actions";
    [["Previous", page - 1, page === 0], ["Next", page + 1, page >= pages - 1]].forEach(([label, target, disabled]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "log-page-button";
      button.dataset.logPage = kind;
      button.dataset.page = String(target);
      button.textContent = label;
      button.disabled = disabled;
      actions.append(button);
    });
    control.append(count, actions);
  }

  function showLog(row) {
    const reader = document.querySelector("[data-log-read]");
    if (!row || !reader) return;
    logOpen = row.id || "";
    reader.hidden = false;
    document.querySelector("[data-log-read-id]").textContent = row.id || "Log";
    const title = row.action || eventLabel(row.event);
    document.querySelector("[data-log-read-title]").textContent = title;
    document.querySelector("[data-log-read-why]").textContent = row.why || "Recorded.";
    const facts = document.querySelector("[data-log-facts]");
    facts.replaceChildren();
    const fields = [
      ["Time", logTime(row.at)],
      ["Service", row.service],
      ["User", row.email],
      ["Actor", [row.actor, row.role].filter(Boolean).join(" · ")],
      ["Target", row.target_id],
      ["Status", row.status === 0 || row.status ? String(row.status) : ""],
      ["Duration", row.duration_ms || row.duration_ms === 0 ? row.duration_ms + " ms" : ""],
      ["Result", resultLabel(row.outcome)],
      ["Error code", row.error_code],
      ["Request id", row.request_id],
      ["Request", row.request],
      ["Response", row.response],
    ];
    fields.forEach(([name, value]) => {
      if (!value || value === "—") return;
      const term = document.createElement("dt");
      term.textContent = name;
      const detail = document.createElement("dd");
      detail.textContent = value;
      if (name === "Request" || name === "Response") detail.className = "log-exchange";
      facts.append(term, detail);
    });
    reader.scrollIntoView({ block: "nearest" });
  }

  function paintLogs() {
    const actions = logRows.actions.filter((row) => logActionService === "all" || row.service === logActionService);
    const actionBody = document.querySelector("[data-log-actions]");
    paintLogPagination("actions", actions.length);
    const actionStart = logPages.actions * LOG_PAGE_SIZE;
    const actionPage = actions.slice(actionStart, actionStart + LOG_PAGE_SIZE);
    if (!logRows.actions.length) emptyLog(actionBody, "No account activity recorded yet.");
    else if (!actions.length) emptyLog(actionBody, "No account activity matches this filter.");
    else {
      actionBody.replaceChildren();
      actionPage.forEach((row) => {
        actionBody.appendChild(logCard(row, "actions"));
      });
    }
    const api = logRows.api.filter((row) => logApiService === "all" || row.service === logApiService);
    const apiBody = document.querySelector("[data-log-api]");
    paintLogPagination("api", api.length);
    const apiStart = logPages.api * LOG_PAGE_SIZE;
    const apiPage = api.slice(apiStart, apiStart + LOG_PAGE_SIZE);
    if (!logRows.api.length) emptyLog(apiBody, "No provider or API activity recorded yet.");
    else if (!api.length) emptyLog(apiBody, "No provider or API activity matches this filter.");
    else {
      apiBody.replaceChildren();
      apiPage.forEach((row) => {
        apiBody.appendChild(logCard(row, "api"));
      });
    }
    document.querySelectorAll("[data-log-filters]").forEach((bar) => {
      const current = bar.dataset.logFilters === "actions" ? logActionService : logApiService;
      bar.querySelectorAll("[data-log-service]").forEach((button) => {
        button.classList.toggle("is-on", button.dataset.logService === current);
      });
    });
    const open = [...logRows.actions, ...logRows.api].find((row) => row.id === logOpen);
    if (open) showLog(open);
  }

  async function loadLogs() {
    const result = await call("/api/auth/desk/logs");
    if (!result.ok) {
      logRows = { actions: [], api: [] };
      logPages.actions = 0;
      logPages.api = 0;
      emptyLog(document.querySelector("[data-log-actions]"), result.data.error || "Could not load logs.");
      emptyLog(document.querySelector("[data-log-api]"), result.data.error || "Could not load logs.");
      document.querySelectorAll("[data-log-pagination]").forEach((control) => control.replaceChildren());
      return;
    }
    logRows = {
      actions: result.data.actions || [],
      api: result.data.api || [],
    };
    paintLogs();
  }

  const sidebar = document.querySelector(".sidebar");
  const backdrop = document.querySelector(".backdrop");
  const menuBtn = document.querySelector(".menu-btn");

  function setNav(open) {
    sidebar.classList.toggle("is-open", open);
    backdrop.hidden = !open;
    menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    menuBtn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  }

  function closeMenus() {
    document.querySelectorAll(".menu").forEach((menu) => {
      menu.hidden = true;
      menu.classList.remove("is-up");
    });
    document.querySelectorAll("[data-more]").forEach((button) => {
      button.setAttribute("aria-expanded", "false");
    });
  }

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".more")) closeMenus();
    if (event.target.id === "confirm") return settleConfirm(false);
    if (event.target.id === "password-modal") return settlePassword(false);
    if (event.target.closest("[data-confirm-cancel]")) return settleConfirm(false);
    if (event.target.closest("[data-confirm-ok]")) return settleConfirm(true);
    if (event.target.closest("[data-password-cancel]")) return settlePassword(false);
    const reveal = event.target.closest("[data-reveal]");
    if (reveal) {
      const input = reveal.parentElement.querySelector("input");
      const shown = input.type === "text";
      input.type = shown ? "password" : "text";
      reveal.setAttribute("aria-label", shown ? "Show password" : "Hide password");
      reveal.querySelectorAll("svg").forEach((icon) => {
        if (icon.hasAttribute("hidden")) icon.removeAttribute("hidden");
        else icon.setAttribute("hidden", "");
      });
      return;
    }
    const next = event.target.closest("[data-show]");
    if (next) show(next.dataset.show);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const reader = document.querySelector("[data-log-read]");
    if (reader && !reader.hidden) {
      reader.hidden = true;
      logOpen = "";
      paintLogs();
    }
    closeMenus();
    if (!document.getElementById("confirm").hidden) settleConfirm(false);
    if (!document.getElementById("password-modal").hidden) settlePassword(false);
    if (sidebar.classList.contains("is-open")) setNav(false);
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

  document.querySelector("[data-log-copy]")?.addEventListener("click", async () => {
    const row = [...logRows.actions, ...logRows.api].find((item) => item.id === logOpen);
    if (!row) return;
    const text = logQuote(row);
    try {
      await navigator.clipboard.writeText(text);
      notify("Copied " + row.id);
    } catch (error) {
      notify("Copy failed. Read " + row.id + " on this screen.");
    }
  });

  document.querySelector(".log-stack")?.addEventListener("click", (event) => {
    if (event.target.closest("[data-log-close]")) {
      document.querySelector("[data-log-read]").hidden = true;
      logOpen = "";
      paintLogs();
      return;
    }
    const button = event.target.closest("[data-log-open]");
    if (!button) return;
    const rows = button.dataset.logKind === "actions" ? logRows.actions : logRows.api;
    const row = rows.find((item) => item.id === button.dataset.logOpen);
    if (!row) return;
    showLog(row);
    paintLogs();
  });

  document.querySelectorAll("[data-log-filters]").forEach((bar) => {
    bar.addEventListener("click", (event) => {
      const button = event.target.closest("[data-log-service]");
      if (!button) return;
      if (bar.dataset.logFilters === "actions") logActionService = button.dataset.logService;
      else logApiService = button.dataset.logService;
      logPages[bar.dataset.logFilters] = 0;
      paintLogs();
    });
  });

  document.querySelector(".log-stack")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-log-page]");
    if (!button || button.disabled) return;
    logPages[button.dataset.logPage] = Number(button.dataset.page) || 0;
    paintLogs();
  });

  document.getElementById("content")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-jump]");
    if (!button || !document.getElementById("content").contains(button)) return;
    room(button.dataset.jump);
    document.getElementById("content").focus();
  });

  document.querySelectorAll("[data-account-view]").forEach((button) => {
    button.addEventListener("click", () => {
      room(button.dataset.accountView);
      document.getElementById("content").focus();
    });
  });

  document.querySelectorAll(".nav").forEach((nav) => {
    nav.addEventListener("click", (event) => {
      const button = event.target.closest("[data-room]");
      if (!button) return;
      room(button.dataset.room);
      document.getElementById("content").focus();
    });
  });

  window.addEventListener("hashchange", () => {
    if (document.getElementById("home").hidden) return;
    const saved = readDeskRoute();
    if (
      saved.room === currentRoom
      && (saved.room !== "payswap" || (saved.payswap === payswapView && saved.econ === econView))
    ) {
      return;
    }
    payswapView = saved.payswap;
    econView = saved.econ;
    room(saved.room, { restore: true });
  });

  function notify(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(notify.timer);
    notify.timer = setTimeout(() => toast.classList.remove("show"), 2600);
  }

  document.querySelectorAll("[data-toast]").forEach((button) => {
    button.addEventListener("click", () => notify(button.dataset.toast));
  });

  document.getElementById("default-policy-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const enabled_services = Array.from(form.querySelectorAll('input[name="svc"]:checked')).map((el) => el.value);
    const res = await call("/api/auth/desk/entitlements/default", {
      enabled_services,
      allow_wallet_pay: Boolean(form.elements.allow_wallet_pay?.checked),
      allow_pg_pay: Boolean(form.elements.allow_pg_pay?.checked),
      allow_pg_topup: Boolean(form.elements.allow_pg_topup?.checked),
      pg_provider: form.elements.pg_provider?.value || "both",
      bbps_pipe: form.elements.bbps_pipe?.value || "mobikwik",
      bbps_bulk_enabled: Boolean(form.elements.bbps_bulk_enabled?.checked),
      default_per_txn_limit: form.elements.default_per_txn_limit?.value,
      default_daily_debit_limit: form.elements.default_daily_debit_limit?.value,
      default_min_balance: form.elements.default_min_balance?.value,
    });
    if (!res.ok) return notify(res.data.error || "Could not save default policy.");
    notify("Default retailer policy saved.");
    payswapView = "policy";
    loadPayswap();
  });

  let currentCommService = "bbps";
  const COMM_RATE_PAGE = 10;
  const COMM_PASS_PAGE = 10;
  const COMM_REV_PAGE = 8;
  let commRates = [];
  let commRatePage = 0;
  let commPassPage = 0;
  let commRevenueRows = [];
  let commRevenuePage = 0;
  let commRateKey = "";
  let commRevenueKey = "";
  let commAdminPct = "30";
  let commRetPct = "70";
  let commRateSvc = "bbps";

  function currentCommMonth() {
    const view = document.querySelector("[data-econ-view]:not([hidden])");
    const el = (view && view.querySelector("[data-comm-month]")) || document.querySelector("[data-comm-month]");
    if (el && el.value) return el.value;
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  }

  function showEconView(name) {
    econView = name || "hub";
    document.querySelectorAll("[data-econ-view]").forEach((node) => {
      node.hidden = node.getAttribute("data-econ-view") !== econView;
    });
    if (currentRoom === "payswap" && payswapView === "commission") {
      document.getElementById("crumb").textContent = deskCrumb("payswap");
      writeDeskRoute();
    }
  }

  function setCommService(service) {
    currentCommService = String(service || "bbps");
    document.querySelectorAll("[data-comm-service]").forEach((btn) => {
      btn.classList.toggle("is-on", btn.dataset.commService === currentCommService);
    });
    const note = document.querySelector("[data-comm-service-note]");
    if (note) {
      if (currentCommService === "bbps") {
        note.textContent = "BBPS uses Mobikwik B2B rates (vendor share). Import updates ServiceRateRow.";
      } else if (currentCommService === "all") {
        note.textContent = "Revenue and TDS roll up every service with settlements.";
      } else {
        note.textContent = `${currentCommService.toUpperCase()} catalogue empty until that service sheet is imported. Policy still editable for future go-live.`;
      }
    }
  }

  function money3(n) {
    const v = Number(n);
    if (!Number.isFinite(v)) return "0.000";
    return v.toFixed(3);
  }

  function updateCommSplitExample() {
    const form = document.getElementById("commission-policy-form");
    if (!form) return;
    const adminPct = Math.max(0, Math.min(100, Number(form.elements.admin_share_percent?.value || 0)));
    const sample = 2.25;
    const adminKeeps = (sample * adminPct) / 100;
    const retailerGets = sample - adminKeeps;
    const adminEl = document.querySelector("[data-comm-ex-admin]");
    const retEl = document.querySelector("[data-comm-ex-retailer]");
    const blurb = document.querySelector("[data-comm-split-blurb]");
    const mode = form.elements.monetization_mode?.value || "vendor_share";
    if (adminEl) adminEl.textContent = `₹${money3(adminKeeps)}`;
    if (retEl) retEl.textContent = `₹${money3(retailerGets)}`;
    if (blurb) {
      blurb.textContent =
        mode === "service_charge"
          ? "Customer service charge mode bills a fee on the transaction. Admin share still drives the default retailer pass-through for vendor-share rows."
          : "Admin share is retained from vendor commission. The remainder is the retailer’s default pass-through until a per-account override is set.";
    }
    const example = document.querySelector("[data-comm-split-example]");
    if (example) example.hidden = mode === "service_charge";
  }

  function fillCommissionPolicyForm(p) {
    if (!p) return;
    const comm = document.getElementById("commission-policy-form");
    if (comm) {
      if (comm.elements.monetization_mode) {
        comm.elements.monetization_mode.value = p.monetization_mode || "vendor_share";
      }
      if (comm.elements.admin_share_percent) {
        comm.elements.admin_share_percent.value = p.admin_share_percent ?? 30;
      }
    }
    updateCommSplitExample();
    const tds = document.getElementById("tds-policy-form");
    if (tds) {
      if (tds.elements.tds_rate_percent) tds.elements.tds_rate_percent.value = p.tds_rate_percent ?? 2;
      if (tds.elements.tds_threshold) tds.elements.tds_threshold.value = p.tds_threshold || "20000";
      if (tds.elements.withhold_tds_always) {
        tds.elements.withhold_tds_always.checked = p.withhold_tds_always !== false;
      }
      if (tds.elements.deductor_tan && p.deductor_tan != null) {
        tds.elements.deductor_tan.value = p.deductor_tan;
      }
      if (tds.elements.no_pan_tds_rate_percent && p.no_pan_tds_rate_percent != null) {
        tds.elements.no_pan_tds_rate_percent.value = p.no_pan_tds_rate_percent;
      }
    }
    const gst = document.getElementById("gst-policy-form");
    if (gst && gst.elements.gst_rate_percent) {
      gst.elements.gst_rate_percent.value = p.gst_rate_percent ?? 18;
    }
  }

  function syncCommImportVisibility() {
    const btn = document.querySelector("[data-comm-import]");
    if (!btn) return;
    const bbps = currentCommService === "bbps";
    btn.hidden = !bbps;
    btn.disabled = !bbps;
  }

  async function loadCommissionPolicy() {
    const svc = currentCommService === "all" ? "bbps" : currentCommService || "bbps";
    const res = await call("/api/auth/desk/commission/policy?service=" + encodeURIComponent(svc));
    if (!res.ok) return;
    fillCommissionPolicyForm(res.data);
    syncCommImportVisibility();
  }

  async function loadCommissionRates() {
    const box = document.querySelector("[data-comm-rates-table]");
    const retailerBox = document.querySelector("[data-comm-retailer-default-table]");
    const banner = document.querySelector("[data-comm-split-banner]");
    const summary = document.querySelector("[data-comm-rates-summary]");
    if (!box) return;
    box.innerHTML = `<div class="commission-empty"><strong>Loading catalogue…</strong><p>Fetching Mobikwik BBPS rates for the selected filters.</p></div>`;
    if (retailerBox) {
      retailerBox.innerHTML = `<div class="commission-empty"><strong>Loading pass-through…</strong><p>Derived once rates arrive.</p></div>`;
    }
    if (summary) summary.hidden = true;
    if (banner) {
      banner.hidden = true;
      banner.textContent = "";
    }
    const svc = currentCommService === "all" ? "bbps" : currentCommService;
    const q = String(document.querySelector("[data-comm-rates-q]")?.value || "").trim();
    const category = String(document.querySelector("[data-comm-rates-category]")?.value || "").trim();
    const qs = new URLSearchParams({ service: svc, limit: category || q ? "500" : "200" });
    if (q) qs.set("q", q);
    if (category) qs.set("category", category);
    let res = await call("/api/auth/desk/commission/rates?" + qs.toString());
    // Empty BBPS catalogue → import sheet once, then reload table.
    if (res.ok && svc === "bbps" && !(res.data.rates || []).length && !q && !category) {
      const imp = await call("/api/auth/desk/commission/rates/import", {});
      if (imp.ok) res = await call("/api/auth/desk/commission/rates?" + qs.toString());
    }
    if (!res.ok) {
      const fail = `<div class="commission-empty"><strong>Could not load rates</strong><p>${escHtml(res.data.error || "Mobikwik BBPS table failed. Try Load rates again.")}</p></div>`;
      box.innerHTML = fail;
      if (retailerBox) retailerBox.innerHTML = fail;
      return;
    }
    if (res.data.policy) fillCommissionPolicyForm(res.data.policy);
    const policy = res.data.policy || {};
    const adminPct = policy.admin_share_percent ?? 30;
    const retPct = policy.retailer_share_percent ?? 70;
    const linked = res.data.linked != null ? res.data.linked : res.data.with_rate;
    const unlinked = res.data.unlinked != null ? res.data.unlinked : res.data.without_rate;
    const total = res.data.total || 0;
    if (summary) {
      summary.hidden = false;
      summary.innerHTML = `
        <article class="commission-stat"><strong>${escHtml(String(total))}</strong><span>Billers in view</span></article>
        <article class="commission-stat"><strong>${escHtml(String(linked ?? "—"))}</strong><span>Linked / with rate</span></article>
        <article class="commission-stat"><strong>${escHtml(String(unlinked ?? "—"))}</strong><span>Missing rate</span></article>
        <article class="commission-stat"><strong>${escHtml(String(adminPct))}% / ${escHtml(String(retPct))}%</strong><span>Default admin / retailer</span></article>`;
    }
    if (banner) {
      banner.hidden = false;
      banner.textContent = category
        ? `Category filter lists every BBPS biller in ${category}. Settlement only starts after a biller is linked with a rate.`
        : "Biller ID is the BBPS operator code. Save changes row by row.";
    }
    syncCommImportVisibility();
    const rates = res.data.rates || [];
    const rateKey = `${svc}|${q}|${category}`;
    if (rateKey !== commRateKey) {
      commRatePage = 0;
      commPassPage = 0;
      commRateKey = rateKey;
    }
    commRates = rates;
    commAdminPct = String(adminPct);
    commRetPct = String(retPct);
    commRateSvc = svc;
    if (!rates.length) {
      const empty = `<div class="commission-empty"><strong>No billers in this filter</strong><p>Import the Mobikwik sheet, or set a BBPS category such as ELECTRICITY to list operators.</p></div>`;
      box.innerHTML = empty;
      if (retailerBox) {
        retailerBox.innerHTML = `<div class="commission-empty"><strong>No pass-through rows</strong><p>Rates with a provider amount will appear here.</p></div>`;
      }
      return;
    }
    paintCommissionRates();
  }

  function paintCommPager(host, page, total, size, kind) {
    if (!host) return;
    const pages = Math.max(1, Math.ceil(total / size));
    const safe = Math.min(page, pages - 1);
    const start = total ? safe * size + 1 : 0;
    const end = Math.min((safe + 1) * size, total);
    host.className = "log-pagination";
    if (!total) {
      host.innerHTML = "";
      return;
    }
    host.innerHTML = `<span class="log-page-count">${start}–${end} of ${total}</span>
      <span class="log-page-actions">
        <button type="button" class="log-page-button" data-comm-page="${kind}" data-comm-target="${safe - 1}" ${safe === 0 ? "disabled" : ""}>Previous</button>
        <button type="button" class="log-page-button" data-comm-page="${kind}" data-comm-target="${safe + 1}" ${safe >= pages - 1 ? "disabled" : ""}>Next</button>
      </span>`;
  }

  function paintCommissionRates() {
    const box = document.querySelector("[data-comm-rates-table]");
    const retailerBox = document.querySelector("[data-comm-retailer-default-table]");
    const rates = commRates;
    const pages = Math.max(1, Math.ceil(rates.length / COMM_RATE_PAGE));
    commRatePage = Math.min(commRatePage, pages - 1);
    const slice = rates.slice(commRatePage * COMM_RATE_PAGE, (commRatePage + 1) * COMM_RATE_PAGE);
    const vendorRows = slice
      .map((r) => {
        const id = escHtml(r.operator_id || r.external_id || r.bbps_op || "");
        const cat = escHtml(r.bbps_category || r.category || "");
        const rt = r.rate_type === "percent" ? "percent" : "flat";
        const linkedPill = r.bbps_linked ? `<span class="pill success">Linked</span>` : `<span class="pill failed">Unlinked</span>`;
        const hasRate = r.has_rate === false ? `<small>No set rate</small>` : "";
        return `<tr data-external-id="${id}" data-rate-name="${escHtml(r.bbps_name || r.operator_name || r.name || "")}" data-category="${cat}" data-service="${escHtml(commRateSvc)}">
        <td class="commission-biller-cell"><strong>${escHtml(r.bbps_name || r.operator_name || r.name || "Unnamed biller")}</strong><span class="mono">${id}</span>${linkedPill} ${hasRate}</td>
        <td><span class="commission-category">${cat || "Uncategorised"}</span></td>
        <td><div class="commission-rate-editor"><input class="commission-rate-value" type="number" step="0.000001" min="0" data-rate-value value="${escHtml(r.rate_value)}" /><select data-rate-type><option value="flat" ${rt === "flat" ? "selected" : ""}>₹ flat</option><option value="percent" ${rt === "percent" ? "selected" : ""}>Percent</option></select></div><small>Set sample ₹${escHtml(r.we_receive_sample || "0.00")}</small></td>
        <td><div class="commission-split"><span><b>${escHtml(String(r.admin_share_percent ?? commAdminPct))}%</b> Admin <small>₹${escHtml(r.admin_keeps_sample || "0.00")}</small></span><span><b>${escHtml(String(r.retailer_share_percent ?? commRetPct))}%</b> Retailer <small>₹${escHtml(r.retailer_gets_sample || "0.00")}</small></span></div></td>
        <td><label class="commission-minimum"><span>Min amount</span><input class="commission-rate-min" type="number" step="0.01" min="0" data-rate-min value="${escHtml(r.min_txn || "0.00")}" /></label></td>
        <td><div class="commission-row-actions"><label class="commission-switch"><input type="checkbox" data-rate-enabled ${r.enabled || r.bbps_enabled ? "checked" : ""} /><span>Enabled</span></label><button type="button" class="btn-xs primary" data-rate-save>Save</button></div></td>
      </tr>`;
      })
      .join("");
    if (box) {
      box.innerHTML = `<div class="commission-scroll"><table class="commission-table"><thead><tr>
        <th>Biller</th><th>Category</th><th>Set rate</th><th>Set split</th><th>Limit</th><th>Availability</th>
      </tr></thead><tbody>${vendorRows}</tbody></table></div>
      <div data-comm-rate-pager></div>`;
      paintCommPager(box.querySelector("[data-comm-rate-pager]"), commRatePage, rates.length, COMM_RATE_PAGE, "rates");
      box.querySelectorAll("[data-rate-save]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const tr = btn.closest("tr");
          if (!tr) return;
          btn.disabled = true;
          const body = {
            service: tr.dataset.service || commRateSvc,
            external_id: tr.dataset.externalId || "",
            category: tr.dataset.category || "",
            name: tr.dataset.rateName || "",
            rate_value: tr.querySelector("[data-rate-value]")?.value,
            rate_type: tr.querySelector("[data-rate-type]")?.value || "flat",
            min_txn: tr.querySelector("[data-rate-min]")?.value,
            enabled: Boolean(tr.querySelector("[data-rate-enabled]")?.checked),
          };
          const saveRes = await call("/api/auth/desk/commission/rates", body);
          btn.disabled = false;
          if (!saveRes.ok) return notify(saveRes.data.error || "Could not save rate row.");
          notify(`Saved biller ${body.external_id}`);
          loadCommissionRates();
        });
      });
    }
    if (!retailerBox) return;
    const pass = rates.filter((r) => r.has_rate !== false);
    const passPages = Math.max(1, Math.ceil(pass.length / COMM_PASS_PAGE) || 1);
    commPassPage = Math.min(commPassPage, passPages - 1);
    const passSlice = pass.slice(commPassPage * COMM_PASS_PAGE, (commPassPage + 1) * COMM_PASS_PAGE);
    if (!pass.length) {
      retailerBox.innerHTML = `<div class="commission-empty"><strong>No pass-through rows</strong><p>Billers with a set rate will show the default retailer share here.</p></div>`;
      return;
    }
    const retRows = passSlice
      .map(
        (r) => `<tr>
        <td class="mono">${escHtml(r.operator_id || r.external_id)}</td>
        <td><strong>${escHtml(r.bbps_name || r.operator_name || r.name || "—")}</strong></td>
        <td><span class="commission-category">${escHtml(r.bbps_category || r.category || "—")}</span></td>
        <td>${escHtml(String(r.retailer_share_percent ?? commRetPct))}%</td>
        <td>₹${escHtml(r.retailer_gets_sample || "0.00")}</td>
      </tr>`
      )
      .join("");
    retailerBox.innerHTML = `<p class="commission-table-meta">Set retailer share ${escHtml(commRetPct)}% · this sample is not settled money</p>
      <div class="commission-scroll"><table class="commission-pass-table"><thead><tr>
        <th>Biller ID</th><th>Name</th><th>Category</th><th>Set share</th><th>Set sample</th>
      </tr></thead><tbody>${retRows}</tbody></table></div>
      <div data-comm-pass-pager></div>`;
    paintCommPager(retailerBox.querySelector("[data-comm-pass-pager]"), commPassPage, pass.length, COMM_PASS_PAGE, "pass");
  }

  async function loadCommissionRevenue() {
    const month = currentCommMonth();
    const monthEl = document.querySelector("[data-comm-month]");
    if (monthEl && !monthEl.value) monthEl.value = month;
    const totalsBox = document.querySelector("[data-comm-revenue-totals]");
    const table = document.querySelector("[data-comm-revenue-table]");
    const svc = currentCommService || "all";
    const res = await call(
      `/api/auth/desk/commission/revenue?month=${encodeURIComponent(month)}&service=${encodeURIComponent(svc)}&limit=200`,
    );
    if (!res.ok) {
      if (table) table.innerHTML = `<p class="note">${escHtml(res.data.error || "Could not load revenue.")}</p>`;
      return;
    }
    const revenueKey = `${month}|${svc}`;
    if (revenueKey !== commRevenueKey) {
      commRevenuePage = 0;
      commRevenueKey = revenueKey;
    }
    const t = res.data.totals || {};
    const title = document.querySelector("[data-comm-revenue-title]");
    const blurb = document.querySelector("[data-comm-revenue-blurb]");
    if (title) title.textContent = svc === "all" ? "Settlement revenue (all services)" : `Settlement revenue · ${svc.toUpperCase()}`;
    if (blurb) {
      blurb.textContent = "Grey is the rate that was set. Green is the commission that settled on that bill.";
    }
    const form = document.getElementById("commission-policy-form");
    const setAdmin = String(form?.elements.admin_share_percent?.value || commAdminPct || "—");
    const setRetailer = Number.isFinite(Number(setAdmin)) ? String(Math.round((100 - Number(setAdmin)) * 100) / 100) : "—";
    if (totalsBox) {
      totalsBox.innerHTML = `
        <article class="commission-fact is-set">
          <span>Set</span>
          <strong>${escHtml(setAdmin)}% / ${escHtml(setRetailer)}%</strong>
          <small>Admin / retailer share configured for this service</small>
        </article>
        <div class="payswap-revenue-stats">
          <article class="card"><strong>${escHtml(String(t.txn_count || 0))}</strong><p>Settled bills</p></article>
          <article class="card"><strong>₹${escHtml(t.vendor_commission || "0.00")}</strong><p>Settled commission</p></article>
          <article class="card"><strong>₹${escHtml(t.admin_revenue || "0.00")}</strong><p>Admin kept</p></article>
          <article class="card"><strong>₹${escHtml(t.retailer_commission || "0.00")}</strong><p>Retailer gross</p></article>
          <article class="card"><strong>₹${escHtml(t.net_credited || "0.00")}</strong><p>Credited after TDS</p></article>
        </div>`;
    }
    commRevenueRows = res.data.recent || [];
    paintCommissionRevenue();
  }

  function paintCommissionRevenue() {
    const table = document.querySelector("[data-comm-revenue-table]");
    if (!table) return;
    const rows = commRevenueRows;
    if (!rows.length) {
      table.innerHTML = `<div class="commission-empty"><strong>No settlements for this filter</strong><p>Revenue rows appear after successful collections in the selected month.</p></div>`;
      return;
    }
    const pages = Math.max(1, Math.ceil(rows.length / COMM_REV_PAGE));
    commRevenuePage = Math.min(commRevenuePage, pages - 1);
    const slice = rows.slice(commRevenuePage * COMM_REV_PAGE, (commRevenuePage + 1) * COMM_REV_PAGE);
    table.innerHTML = `<div class="commission-scroll"><table class="commission-table commission-revenue-table"><thead><tr>
        <th>Bill</th><th>Set rate</th><th>Settled</th><th>Wallet</th>
      </tr></thead><tbody>${slice
        .map((r) => {
          const who = accountIdForEmail(r.user_id, "retailer") || r.user_id;
          const share = r.set_share ? `Admin ${r.set_share}` : "Set split";
          const tds = Number(r.tds || 0) > 0 ? ` · TDS ₹${r.tds}` : "";
          return `<tr>
            <td class="commission-biller-cell"><strong>${escHtml(who)}</strong><span class="mono">${escHtml(r.reference)}</span><small>${escHtml(r.service || "")} · ₹${escHtml(r.amount)}</small></td>
            <td><div class="commission-fact is-set"><span>Set</span><strong>${escHtml(r.set_label || "No sheet rate")}</strong><small>${escHtml(share)}</small></div></td>
            <td><div class="commission-fact is-settled"><span>Settled</span><strong>₹${escHtml(r.vendor_commission || "0.00")}</strong><small>Admin ₹${escHtml(r.admin_revenue)} · Retailer ₹${escHtml(r.retailer_commission)}${escHtml(tds)}</small></div></td>
            <td class="num"><strong>₹${escHtml(r.net_credit)}</strong><small>After TDS</small></td>
          </tr>`;
        })
        .join("")}</tbody></table></div>
      <div data-comm-rev-pager></div>`;
    paintCommPager(table.querySelector("[data-comm-rev-pager]"), commRevenuePage, rows.length, COMM_REV_PAGE, "revenue");
  }

  function tdsChallanBody(month, email, amount) {
    return {
      month,
      email: email || "",
      challan_bsr: String(document.querySelector("[data-comm-tds-bsr]")?.value || "").trim(),
      challan_serial: String(document.querySelector("[data-comm-tds-serial]")?.value || "").trim(),
      challan_date: String(document.querySelector("[data-comm-tds-date]")?.value || "").trim(),
      challan_amount: amount,
    };
  }

  async function loadCommissionTds() {
    const month = currentCommMonth();
    const box = document.querySelector("[data-comm-tds-table]");
    if (!box) return;
    const res = await call(`/api/auth/desk/commission/tds?month=${encodeURIComponent(month)}`);
    if (!res.ok) {
      box.innerHTML = `<p class="note">${escHtml(res.data.error || "Could not load TDS.")}</p>`;
      return;
    }
    const retailers = res.data.retailers || [];
    const totals = res.data.totals || {};
    const amount = document.querySelector("[data-comm-tds-amount]");
    if (amount && document.activeElement !== amount) amount.value = totals.open || "0.00";
    const period = [res.data.section || "194H", res.data.quarter, res.data.financial_year ? `FY ${res.data.financial_year}` : ""]
      .filter(Boolean)
      .join(" · ");
    const tan = res.data.deductor_tan ? `TAN ${res.data.deductor_tan}` : "TAN missing";
    const gaps = (res.data.missing || []).map((line) => `<p class="note">${escHtml(line)}</p>`).join("");
    if (!retailers.length) {
      box.innerHTML = `<p class="note">${escHtml(month)} · ${escHtml(period)} · ${escHtml(tan)}. No TDS rows. Open ₹${escHtml(totals.open || "0.00")}.</p>${gaps}`;
      return;
    }
    box.innerHTML = `<p class="note">${escHtml(month)} · ${escHtml(period)} · ${escHtml(tan)} · total ₹${escHtml(totals.tds || "0.00")} · open ₹${escHtml(totals.open || "0.00")}</p>
      ${gaps}
      <table><thead><tr><th>Retailer</th><th>PAN</th><th>Credit</th><th>Txns</th><th>Commission</th><th>TDS</th><th>Open</th><th>Challan</th><th></th></tr></thead>
      <tbody>${retailers
        .map((r) => {
          const who = r.name ? `${r.name} · ${r.user_id}` : r.user_id;
          const pan = r.pan || r.pan_mask || "Missing";
          const credit = r.credited_from ? (r.credited_from === r.credited_to ? r.credited_from : `${r.credited_from} – ${r.credited_to}`) : "—";
          const challan = r.challan_bsr
            ? `${r.challan_bsr} / ${r.challan_serial || "—"} / ${r.challan_date || "—"}`
            : "—";
          const deposit = Number(r.open_paise || 0) > 0
            ? `<button type="button" class="select" data-comm-tds-deposit="${escHtml(r.user_id)}" data-comm-tds-open="${escHtml(r.open)}">Deposit</button>`
            : "Deposited";
          return `<tr>
          <td>${escHtml(who)}</td>
          <td class="mono">${escHtml(pan)}</td>
          <td>${escHtml(credit)}</td>
          <td>${escHtml(String(r.count || 0))}</td>
          <td>₹${escHtml(r.commission)}</td>
          <td>₹${escHtml(r.tds)} · ${escHtml(r.tds_basis_label || "194H")}</td>
          <td>₹${escHtml(r.open)}</td>
          <td>${escHtml(challan)}</td>
          <td>${deposit}</td>
        </tr>`;
        })
        .join("")}</tbody></table>`;
    box.querySelectorAll("[data-comm-tds-deposit]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const res2 = await call("/api/auth/desk/commission/tds", tdsChallanBody(month, btn.dataset.commTdsDeposit, btn.dataset.commTdsOpen));
        if (!res2.ok) return notify(res2.data.error || "Could not mark deposited.");
        notify(`Marked ${res2.data.updated || 0} TDS rows deposited.`);
        loadCommissionTds();
      });
    });
  }

  async function loadCommissionInvoices() {
    const box = document.querySelector("[data-comm-inv-table]");
    if (!box) return;
    const email = String(document.querySelector("[data-comm-inv-email]")?.value || "").trim();
    const month = currentCommMonth();
    const qs = new URLSearchParams({ month });
    if (email) qs.set("email", email);
    const res = await call("/api/auth/desk/commission/invoices?" + qs.toString());
    if (!res.ok) {
      box.innerHTML = `<p class="note">${escHtml(res.data.error || "Could not load invoices.")}</p>`;
      return;
    }
    const invoices = res.data.invoices || [];
    if (!invoices.length) {
      box.innerHTML = `<p class="note">No draft invoices for ${escHtml(month)}.</p>`;
      return;
    }
    box.innerHTML = `<table><thead><tr><th>No</th><th>Retailer</th><th>GSTIN</th><th>Taxable</th><th>Total</th><th>Status</th><th></th></tr></thead>
      <tbody>${invoices
        .map(
          (inv) => `<tr>
          <td>${escHtml(inv.invoice_no)}</td>
          <td>${escHtml(inv.user_id)}</td>
          <td>${escHtml(inv.gstin || "—")}</td>
          <td>₹${escHtml(inv.taxable)}</td>
          <td>₹${escHtml(inv.total)}</td>
          <td>${escHtml(inv.status)}</td>
          <td><button type="button" class="select" data-comm-inv-html="${escHtml(inv.invoice_id)}">Open</button></td>
        </tr>`
        )
        .join("")}</tbody></table>`;
    const byId = Object.fromEntries(invoices.map((inv) => [inv.invoice_id, inv]));
    box.querySelectorAll("[data-comm-inv-html]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const inv = byId[btn.dataset.commInvHtml];
        if (!inv?.html) return;
        const blob = new Blob([String(inv.html)], { type: "text/html;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const w = window.open(url, "_blank", "noopener,noreferrer");
        if (!w) URL.revokeObjectURL(url);
        else window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      });
    });
  }

  async function openEconView(name) {
    showEconView(name || "hub");
    const month = currentCommMonth();
    document.querySelectorAll("[data-comm-month]").forEach((el) => {
      if (!el.value) el.value = month;
    });
    if (econView === "hub") return;
    await loadCommissionPolicy();
    if (econView === "commission") {
      await loadCommissionRates();
      await loadCommissionRevenue();
    } else if (econView === "tds") {
      await loadCommissionTds();
      await loadTdsCertificates();
    } else if (econView === "gst") {
      await loadCommissionInvoices();
    }
  }

  async function loadCommissionDesk() {
    showEconView("hub");
  }

  document.querySelectorAll("[data-econ-open]").forEach((btn) => {
    btn.addEventListener("click", () => openEconView(btn.dataset.econOpen || "hub"));
  });

  document.getElementById("commission-policy-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const svc = currentCommService === "all" ? "bbps" : currentCommService || "bbps";
    const adminPct = Number(form.elements.admin_share_percent.value || 0);
    const res = await call("/api/auth/desk/commission/policy", {
      service: svc,
      monetization_mode: form.elements.monetization_mode?.value || "vendor_share",
      admin_share_bps: Math.round(adminPct * 100),
    });
    if (!res.ok) return notify(res.data.error || "Could not save policy.");
    fillCommissionPolicyForm(res.data);
    notify(`Commission policy saved for ${svc}.`);
    loadCommissionRates();
  });

  document.getElementById("commission-policy-form")?.addEventListener("input", (event) => {
    if (event.target?.name === "admin_share_percent" || event.target?.name === "monetization_mode") {
      updateCommSplitExample();
    }
  });
  document.getElementById("commission-policy-form")?.addEventListener("change", (event) => {
    if (event.target?.name === "monetization_mode") updateCommSplitExample();
  });
  updateCommSplitExample();

  document.getElementById("tds-policy-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const svc = currentCommService === "all" ? "bbps" : currentCommService || "bbps";
    const tdsPct = Number(form.elements.tds_rate_percent.value || 0);
    const threshold = Number(form.elements.tds_threshold.value || 0);
    const res = await call("/api/auth/desk/commission/policy", {
      service: svc,
      tds_rate_bps: Math.round(tdsPct * 100),
      tds_threshold_paise: Math.round(threshold * 100),
      withhold_tds_always: Boolean(form.elements.withhold_tds_always.checked),
      deductor_tan: String(form.elements.deductor_tan?.value || "").trim().toUpperCase(),
      no_pan_tds_rate_bps: Math.round(Number(form.elements.no_pan_tds_rate_percent?.value || 0) * 100),
    });
    if (!res.ok) return notify(res.data.error || "Could not save TDS policy.");
    fillCommissionPolicyForm(res.data);
    notify("TDS policy saved.");
  });

  async function loadTdsCertificates() {
    const box = document.querySelector("[data-tds-cert-table]");
    if (!box) return;
    const res = await call("/api/auth/desk/commission/tds/certificate");
    if (!res.ok) {
      box.innerHTML = `<p class="note">${escHtml(res.data.error || "Could not load certificates.")}</p>`;
      return;
    }
    const rows = res.data.certificates || [];
    if (!rows.length) {
      box.innerHTML = `<p class="note">No certificate requests. Retailers file these from their PaySwap profile.</p>`;
      return;
    }
    box.innerHTML = `<table><thead><tr><th>Retailer</th><th>Certificate</th><th>Rate</th><th>Dates</th><th>PAN</th><th>Status</th><th></th></tr></thead><tbody>${rows
      .map((row) => {
        const who = row.name ? `${row.name} · ${row.user_id}` : row.user_id;
        const actions = row.status === "pending"
          ? `<button type="button" class="primary" data-tds-cert-approve="${escHtml(String(row.id))}">Approve</button> <button type="button" class="select" data-tds-cert-reject="${escHtml(String(row.id))}">Reject</button>`
          : escHtml(row.status === "approved" ? `Approved · refunded ₹${row.refunded || "0.00"}` : row.status);
        return `<tr>
          <td>${escHtml(who)}</td>
          <td class="mono">${escHtml(row.certificate_no || "")}</td>
          <td>${escHtml(String(row.rate_percent ?? ""))}%</td>
          <td>${escHtml(row.valid_from || "")} – ${escHtml(row.valid_to || "")}</td>
          <td>${row.pan_on_file ? "On file" : "Missing"}</td>
          <td>${escHtml(row.status === "rejected" && row.reject_reason ? `rejected · ${row.reject_reason}` : row.status || "")}</td>
          <td>${actions}</td>
        </tr>`;
      })
      .join("")}</tbody></table>`;
    box.querySelectorAll("[data-tds-cert-approve]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const res2 = await call("/api/auth/desk/commission/tds/certificate", { id: Number(btn.dataset.tdsCertApprove), decision: "approve" });
        if (!res2.ok) return notify(res2.data.error || "Could not approve.");
        notify(`Approved. Credited back ₹${res2.data.refunded || "0.00"}.`);
        loadTdsCertificates();
        loadCommissionTds();
      });
    });
    box.querySelectorAll("[data-tds-cert-reject]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const reason = window.prompt("Reason for rejection");
        if (reason === null) return;
        const res2 = await call("/api/auth/desk/commission/tds/certificate", {
          id: Number(btn.dataset.tdsCertReject),
          decision: "reject",
          reason,
        });
        if (!res2.ok) return notify(res2.data.error || "Could not reject.");
        notify("Certificate rejected. The retailer stays on the current rate.");
        loadTdsCertificates();
      });
    });
  }

  document.querySelector("[data-tds-cert-refresh]")?.addEventListener("click", () => loadTdsCertificates());

  document.getElementById("gst-policy-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const svc = currentCommService === "all" ? "bbps" : currentCommService || "bbps";
    const gstPct = Number(form.elements.gst_rate_percent.value || 0);
    const res = await call("/api/auth/desk/commission/policy", {
      service: svc,
      gst_rate_bps: Math.round(gstPct * 100),
    });
    if (!res.ok) return notify(res.data.error || "Could not save GST policy.");
    fillCommissionPolicyForm(res.data);
    notify("GST policy saved.");
  });

  document.querySelector("[data-comm-import]")?.addEventListener("click", async () => {
    if (currentCommService !== "bbps") {
      notify("Mobikwik B2B import is only for the BBPS tab.");
      return;
    }
    const res = await call("/api/auth/desk/commission/rates/import", {});
    if (!res.ok) return notify(res.data.error || "Import failed.");
    notify(`Imported ${res.data.upserted || 0} rates (skipped ${res.data.skipped || 0}).`);
    loadCommissionRates();
  });
  document.querySelectorAll("[data-comm-service]").forEach((btn) => {
    btn.addEventListener("click", () => {
      setCommService(btn.dataset.commService);
      loadCommissionPolicy();
      loadCommissionRates();
      loadCommissionRevenue();
    });
  });
  document.querySelector("[data-comm-rates-refresh]")?.addEventListener("click", () => loadCommissionRates());
  document.querySelector("[data-comm-rates-q]")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadCommissionRates();
  });
  document.querySelector("[data-comm-rates-category]")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadCommissionRates();
  });
  document.querySelector("[data-comm-rates-category]")?.addEventListener("change", () => loadCommissionRates());
  document.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-comm-page]");
    if (!btn || btn.disabled) return;
    const target = Number(btn.dataset.commTarget);
    if (!Number.isFinite(target) || target < 0) return;
    const kind = btn.dataset.commPage;
    if (kind === "rates") commRatePage = target;
    else if (kind === "pass") commPassPage = target;
    else if (kind === "revenue") commRevenuePage = target;
    else if (kind === "retailer-sheet") retailerSheetPage = target;
    else return;
    if (kind === "revenue") paintCommissionRevenue();
    else if (kind === "retailer-sheet") paintRetailerBillerSheet();
    else paintCommissionRates();
  });
  document.addEventListener("click", async (event) => {
    const save = event.target.closest("[data-biller-save]");
    const clear = event.target.closest("[data-biller-clear]");
    const btn = save || clear;
    if (!btn || btn.disabled) return;
    const tr = btn.closest("tr");
    const externalId = tr?.dataset.billerId || "";
    const category = tr?.dataset.billerCategory || "";
    if (!externalId || !retailerSheetEmail) return;
    const body = {
      email: retailerSheetEmail,
      service: retailerSheetService,
      external_id: externalId,
      category,
    };
    if (clear) body.clear_share = true;
    else {
      const raw = tr.querySelector("[data-biller-share]")?.value;
      if (raw === "" || raw == null) {
        notify("Enter the admin share for this biller, or use Inherit.");
        return;
      }
      const pct = Number(raw);
      if (Number.isNaN(pct) || pct < 0 || pct > 100) {
        notify("Admin share must be 0–100.");
        return;
      }
      body.admin_share_bps = Math.round(pct * 100);
    }
    btn.disabled = true;
    const res = await call("/api/auth/desk/commission/retailer", body);
    btn.disabled = false;
    if (!res.ok) return notify(res.data.error || "Could not save this biller share.");
    const retailerId = accountIdForEmail(retailerSheetEmail, "retailer") || retailerSheetEmail;
    notify(clear ? `${retailerId} · ${externalId} now inherits Economics.` : `${retailerId} · ${externalId} share saved.`);
    loadRetailerBillerSheet();
  });

  document.querySelector("[data-comm-revenue-refresh]")?.addEventListener("click", () => {
    loadCommissionRevenue();
  });
  document.querySelector("[data-comm-tds-refresh]")?.addEventListener("click", () => loadCommissionTds());
  document.querySelector("[data-comm-tds-deposit-all]")?.addEventListener("click", async () => {
    const month = currentCommMonth();
    const amount = String(document.querySelector("[data-comm-tds-amount]")?.value || "").trim();
    const res = await call("/api/auth/desk/commission/tds", tdsChallanBody(month, "", amount));
    if (!res.ok) return notify(res.data.error || "Could not mark deposited.");
    notify(`Marked ${res.data.updated || 0} TDS rows deposited.`);
    loadCommissionTds();
  });
  document.querySelector("[data-comm-retailer-load]")?.addEventListener("click", async () => {
    const email = String(document.querySelector("[data-comm-retailer-email]")?.value || "").trim().toLowerCase();
    const note = document.querySelector("[data-comm-retailer-note]");
    if (!email) return notify("Enter retailer email.");
    const res = await call("/api/auth/desk/commission/retailer?email=" + encodeURIComponent(email));
    if (!res.ok) return notify(res.data.error || "Could not load override.");
    const share = document.querySelector("[data-comm-retailer-share]");
    if (share) share.value = res.data.admin_share_percent ?? "";
    if (note) {
      note.textContent = res.data.active
        ? `Override active. Inherit default share bps=${res.data.inherits_admin_share_bps}.`
        : `No active override — inherits default ${res.data.inherits_admin_share_bps} bps.`;
    }
  });
  document.querySelector("[data-comm-retailer-save]")?.addEventListener("click", async () => {
    const email = String(document.querySelector("[data-comm-retailer-email]")?.value || "").trim().toLowerCase();
    const shareRaw = document.querySelector("[data-comm-retailer-share]")?.value;
    if (!email) return notify("Enter retailer email.");
    const body = { email, active: true };
    if (shareRaw !== "" && shareRaw != null) body.admin_share_bps = Math.round(Number(shareRaw) * 100);
    const res = await call("/api/auth/desk/commission/retailer", body);
    if (!res.ok) return notify(res.data.error || "Could not save override.");
    notify("Retailer commission override saved.");
  });
  document.querySelector("[data-comm-retailer-clear]")?.addEventListener("click", async () => {
    const email = String(document.querySelector("[data-comm-retailer-email]")?.value || "").trim().toLowerCase();
    if (!email) return notify("Enter retailer email.");
    const res = await call("/api/auth/desk/commission/retailer", { email, clear_share: true, active: true });
    if (!res.ok) return notify(res.data.error || "Could not clear share.");
    const share = document.querySelector("[data-comm-retailer-share]");
    if (share) share.value = "";
    notify("Retailer share reset to default.");
  });
  document.querySelector("[data-comm-inv-create]")?.addEventListener("click", async () => {
    const email = String(document.querySelector("[data-comm-inv-email]")?.value || "").trim().toLowerCase();
    if (!email) return notify("Enter retailer email.");
    const res = await call("/api/auth/desk/commission/invoices", { email, month: currentCommMonth() });
    if (!res.ok) return notify(res.data.error || "Could not create invoice.");
    notify(`Draft invoice ${res.data.invoice_no} created.`);
    loadCommissionInvoices();
  });
  document.querySelector("[data-comm-inv-refresh]")?.addEventListener("click", () => loadCommissionInvoices());

  document.querySelectorAll("[data-payswap-open]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const next = btn.dataset.payswapOpen || "hub";
      showPayswapView(next);
      if (next === "activity") loadPayswapActivity();
      if (next === "bulk") loadBulkDesk();
      if (next === "bbps") {
        if (payswapPolicyCache) fillDefaultBbpsCats(payswapPolicyCache);
        else loadPayswap();
      }
      if (next === "retailers") {
        fillRetailerSvcSelect();
        const sel = document.querySelector("[data-retailer-svc-select]");
        if (sel && sel.value) loadRetailerSvcPanel(sel.value);
      }
      if (next === "policy" && payswapPolicyCache) fillDefaultPolicyForm(payswapPolicyCache);
      if (next === "commission") {
        const econTarget = btn.dataset.econTarget || "";
        if (econTarget && ECON_VIEWS.has(econTarget)) openEconView(econTarget);
        else loadCommissionDesk();
      }
    });
  });

  document.querySelector("[data-bulk-desk-refresh]")?.addEventListener("click", () => loadBulkDesk());
  document.querySelector("[data-bulk-desk-q]")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadBulkDesk();
  });

  document.querySelector("[data-bbps-unrestricted]")?.addEventListener("change", (event) => {
    const on = Boolean(event.currentTarget.checked);
    document.querySelectorAll('input[name="bbps_cat"]').forEach((cb) => {
      cb.disabled = on;
      if (on) cb.checked = true;
    });
    document.querySelector("[data-default-bbps-cats]")?.classList.toggle("is-dimmed", on);
    if (payswapPolicyCache) {
      paintBbpsCatStats({
        ...payswapPolicyCache,
        bbps_categories_unrestricted: on,
      });
    } else {
      paintBbpsCatStats({
        bbps_catalog: Array.from(document.querySelectorAll('input[name="bbps_cat"]')).map((el) => ({ id: el.value })),
        enabled_bbps_categories: Array.from(document.querySelectorAll('input[name="bbps_cat"]:checked')).map((el) => el.value),
        bbps_categories_unrestricted: on,
      });
    }
  });

  document.querySelector("[data-bbps-cat-search]")?.addEventListener("input", filterBbpsCatTiles);

  async function saveBbpsCategories() {
    const unrestricted = Boolean(document.querySelector("[data-bbps-unrestricted]")?.checked);
    const enabled_bbps_categories = unrestricted
      ? []
      : Array.from(document.querySelectorAll('input[name="bbps_cat"]:checked')).map((el) => el.value);
    if (!unrestricted && !enabled_bbps_categories.length) {
      return notify("Pick at least one category, or turn on Show all categories.");
    }
    const res = await call("/api/auth/desk/entitlements/default", { enabled_bbps_categories });
    if (!res.ok) return notify(res.data.error || "Could not save BBPS categories.");
    payswapPolicyCache = res.data;
    fillDefaultBbpsCats(res.data);
    notify(unrestricted ? "All BBPS categories enabled for retailers." : "Default BBPS categories saved.");
  }

  document.querySelectorAll("[data-bbps-cats-save]").forEach((btn) => {
    btn.addEventListener("click", saveBbpsCategories);
  });

  document.querySelector("[data-retailer-svc-load]")?.addEventListener("click", () => {
    const email = document.querySelector("[data-retailer-svc-select]")?.value || "";
    loadRetailerSvcPanel(email);
  });

  document.querySelector("[data-retailer-svc-select]")?.addEventListener("change", (event) => {
    const email = event.currentTarget.value || "";
    if (email) loadRetailerSvcPanel(email);
    else loadRetailerSvcPanel("");
  });

  document.getElementById("admin-wallet-adjust")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector("[type=submit]");
    if (submit) submit.disabled = true;
    const res = await call(
      "/api/auth/desk/wallets/adjust",
      {
        email: form.elements.email?.value.trim(),
        direction: form.elements.direction?.value,
        amount: form.elements.amount?.value,
        reason: form.elements.reason?.value.trim(),
      },
      { "Idempotency-Key": moneyKey() },
    );
    if (submit) submit.disabled = false;
    if (!res.ok) return notify(res.data.error || "Adjustment failed.");
    form.reset();
    notify(res.data.pending ? "Waiting for a second admin to approve this adjustment." : "Wallet adjustment recorded.");
    loadMoney();
  });

  document.querySelectorAll("[data-money-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      moneyFilter = btn.dataset.moneyFilter || "all";
      document.querySelectorAll("[data-money-filter]").forEach((b) => b.classList.toggle("is-on", b === btn));
      paintMoneyLedger();
    });
  });

  document.getElementById("money-ledger-search")?.addEventListener("input", (event) => {
    moneyQuery = event.target.value || "";
    paintMoneyLedger();
  });

  document.querySelectorAll("[data-fund-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      fundTab = btn.dataset.fundTab || "all";
      fundSelectedId = "";
      const detail = document.querySelector("[data-fund-detail]");
      if (detail) detail.hidden = true;
      paintFundRequests();
    });
  });

  document.getElementById("fund-mode-filter")?.addEventListener("change", (event) => {
    fundMode = event.target.value || "all";
    paintFundRequests();
  });

  document.getElementById("fund-req-search")?.addEventListener("input", (event) => {
    fundQuery = event.target.value || "";
    paintFundRequests();
  });

  document.querySelector("[data-fund-detail-close]")?.addEventListener("click", () => {
    fundSelectedId = "";
    const detail = document.querySelector("[data-fund-detail]");
    if (detail) detail.hidden = true;
    paintFundRequests();
  });

  document.querySelectorAll("[data-fund-review-decision]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const form = document.getElementById("fund-detail-review-form");
      const request_id = form?.dataset.requestId || "";
      const decision = btn.dataset.fundReviewDecision;
      if (!request_id || !decision) return;
      const rawNote = form.elements.note?.value.trim() || "";
      const note = rawNote || (decision === "approve" ? "Verified in bank statement" : "UTR not matched in bank statement");
      btn.disabled = true;
      const res = await call("/api/auth/desk/wallets/topup-review", { request_id, decision, note });
      btn.disabled = false;
      if (!res.ok) notify(res.data.error || "Action failed.");
      else notify(`Fund request ${decision}d.`);
      await loadFundRequests();
    });
  });

  document.getElementById("fund-export-csv")?.addEventListener("click", () => {
    const rows = filteredFundRows();
    if (!rows || !rows.length) return notify("No fund requests to export.");
    const flat = rows.map((r) => {
      if (fundTab === "pg") return r;
      const copy = Object.assign({}, r);
      if (copy.ledger_entry) {
        copy.ledger_entry_id = copy.ledger_entry.entry_id;
        copy.balance_before = copy.ledger_entry.balance_before;
        copy.balance_after = copy.ledger_entry.balance_after;
        delete copy.ledger_entry;
      }
      return copy;
    });
    const headers = Object.keys(flat[0]);
    const csv = [
      headers.join(","),
      ...flat.map((r) => headers.map((h) => `"${String(r[h] ?? "").replace(/"/g, '""')}"`).join(",")),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `payswap-fund-requests-${fundTab}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  });

  document.querySelector("[data-report-detail-close]")?.addEventListener("click", () => {
    reportSelectedKey = "";
    const detail = document.querySelector("[data-report-detail]");
    if (detail) detail.hidden = true;
    paintReportsTable();
  });

  document.querySelector("[data-report-detail-sync]")?.addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    const reference = btn.dataset.reference || "";
    const pgOrderId = btn.dataset.pgOrderId || "";
    btn.disabled = true;
    let res;
    if (pgOrderId) {
      res = await call("/api/auth/desk/transactions/pg-sync", { pg_order_id: pgOrderId });
      btn.disabled = false;
      if (!res.ok) notify(res.data.error || "Could not sync PG status.");
      else notify(`PG ${pgOrderId}: ${res.data.status || "synced"}`);
    } else if (reference) {
      res = await call("/api/auth/desk/transactions/bbps-sync", { reference });
      btn.disabled = false;
      if (!res.ok) notify(res.data.error || "Could not sync status.");
      else notify(`BBPS ${reference}: ${res.data.state || "synced"}`);
    } else {
      btn.disabled = false;
      return;
    }
    await loadReports();
  });

  document.getElementById("report-filter-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    reportPage = 0;
    reportSelectedKey = "";
    const detail = document.querySelector("[data-report-detail]");
    if (detail) detail.hidden = true;
    loadReports();
  });

  document.getElementById("report-reset-btn")?.addEventListener("click", () => {
    const form = document.getElementById("report-filter-form");
    if (form) form.reset();
    reportPage = 0;
    reportSelectedKey = "";
    const detail = document.querySelector("[data-report-detail]");
    if (detail) detail.hidden = true;
    loadReports();
  });

  document.querySelectorAll("[data-report-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      reportTab = btn.dataset.reportTab || "bbps";
      reportPage = 0;
      reportSelectedKey = "";
      const detail = document.querySelector("[data-report-detail]");
      if (detail) detail.hidden = true;
      paintReportsTable();
    });
  });

  document.querySelector("[data-report-pagination]")?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-report-page]");
    if (!btn || btn.disabled) return;
    const next = Number(btn.dataset.reportPage);
    if (!Number.isFinite(next) || next < 0) return;
    reportPage = next;
    paintReportsTable();
    document.querySelector("[data-report-table]")?.scrollIntoView({ block: "nearest" });
  });

  function exportReportCsv() {
    const rows = reportRowsForTab();
    const label = (REPORT_TAB_META[reportTab] || {}).title || reportTab;
    if (!rows || !rows.length) return notify(`No ${String(label).toLowerCase()} to export. Apply filters or pick another tab.`);
    const flat = rows.map((r) => {
      const out = {};
      Object.entries(r).forEach(([k, v]) => {
        out[k] = v && typeof v === "object" ? JSON.stringify(v) : v;
      });
      return out;
    });
    const headers = Object.keys(flat[0]);
    const csv = [
      headers.join(","),
      ...flat.map((r) => headers.map((h) => `"${String(r[h] ?? "").replace(/"/g, '""')}"`).join(",")),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `payswap-${reportTab}-report.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    notify(`Exported ${rows.length} ${label.toLowerCase()}.`);
  }

  document.querySelectorAll("[data-report-export]").forEach((btn) => {
    btn.addEventListener("click", exportReportCsv);
  });

  document.getElementById("range")?.addEventListener("change", () => {
    loadOverview();
  });

  document.getElementById("desk-search").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const query = event.target.value.trim();
    if (currentRoom === "people") {
      document.getElementById("people-filter").value = query;
      paintPeople();
      return;
    }
    const match = Object.keys(ROOM_TITLE).find((name) => ROOM_TITLE[name].toLowerCase().includes(query.toLowerCase()));
    if (match) {
      room(match);
      document.getElementById("content").focus();
      return;
    }
    notify("No console section matches “" + query + "”.");
  });

  document.getElementById("people-filter").addEventListener("input", paintPeople);
  document.querySelectorAll("[data-user-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      userFilter = button.dataset.userFilter;
      paintPeople();
    });
  });
  document.querySelectorAll("[data-verify-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      verifyFilter = button.dataset.verifyFilter;
      paintVerifyFilters();
      paintPendingSignups();
      paintVerifiedAccounts();
    });
  });
  document.getElementById("refresh").addEventListener("click", async () => {
    const button = document.getElementById("refresh");
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    await paintDesk({ email: currentEmail(), role: ROLE });
    room(currentRoom, { restore: true });
    button.disabled = false;
    button.removeAttribute("aria-busy");
  });

  menuBtn.addEventListener("click", () => setNav(!sidebar.classList.contains("is-open")));
  backdrop.addEventListener("click", () => setNav(false));

  document.getElementById("logout").addEventListener("click", async () => {
    await call("/api/auth/logout", {});
    show("signed-out");
  });

  document.getElementById("password-modal").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    passwordError("");
    const modal = document.getElementById("password-modal");
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    const result = await call("/api/auth/desk/people/password", {
      user_id: modal.dataset.userId || "",
      email: document.querySelector("[data-password-for]").textContent,
      password: form.password.value,
    });
    submit.disabled = false;
    if (!result.ok) {
      passwordError(result.data.error || "Could not update the password.");
      return;
    }
    settlePassword(true);
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

  function roleLabel(role) {
    if (role === "customer") return "ParkPe customer";
    if (role === "retailer") return "PaySwap retailer";
    return "admin";
  }

  async function finishAddAccount(email, role) {
    const clean = String(email || "").trim();
    addSignup = "";
    const success = addForm.querySelector("[data-add-success]");
    if (success) {
      success.querySelector("[data-add-success-email]").textContent = clean || "—";
      success.querySelector("[data-add-success-role]").textContent = roleLabel(role);
    }
    showAddStep("done");
    notify(clean ? clean + " is ready as " + roleLabel(role) + "." : "Account is ready.");
    await loadPeople();
    loadSignups();
    room("people");
  }

  function showAddStep(step) {
    addStep = step;
    addForm.querySelectorAll("[data-add]").forEach((node) => {
      node.hidden = node.dataset.add !== step;
    });
    const rolePick = addForm.querySelector("[data-role-pick]");
    if (rolePick) rolePick.hidden = step === "done";
    const adminDetails = addAccountRole() === "admin" && step === "details";
    const labels = {
      details: adminDetails ? "Add admin" : "Send codes",
      codes: "Verify email and mobile",
      aadhaar: "Open DigiLocker",
      "aadhaar-done": "Continue to PAN",
      pan: "Check PAN",
      business: "Verify GST and Udyam",
      review: "Approve outlet",
      done: "Add another account",
    };
    const hints = {
      details: adminDetails
        ? "Creates the admin account on this desk."
        : "Sends an email code and an SMS code. The account is created after both codes match.",
      codes: "Enter both codes. A retailer then continues to DigiLocker.",
      aadhaar: "Opens DigiLocker for this retailer. The account is not created yet.",
      "aadhaar-done": "After DigiLocker shows success, this desk checks Cashfree every few seconds. You can also press Continue.",
      pan: "Checks the PAN against the registry. GST and Udyam come next.",
      business: "Stand at the outlet. Cashfree must show an active GSTIN and a live Udyam for the same business.",
      review: "Approving opens sign-in. Until then the retailer cannot enter PaySwap.",
      done: "The new account appears in the list on the left.",
    };
    addForm.querySelector("[data-add-submit]").textContent = labels[step] || "Continue";
    addForm.querySelector("[data-add-hint]").textContent = hints[step] || "";
    const mobile = addForm.querySelector("[data-add-mobile]");
    mobile.hidden = adminDetails || step === "done";
    field("mobile").required = !adminDetails && step === "details";
    if (step === "aadhaar-done") {
      startAadhaarPoll(
        addSignup,
        () => {
          notify("DigiLocker verified.");
          showAddStep("pan");
        },
        (message) => addError(message)
      );
    } else {
      stopAadhaarPoll();
    }
  }

  addForm.querySelectorAll("[data-add-role]").forEach((button) => {
    button.addEventListener("click", () => {
      setAddAccountRole(button.dataset.addRole || "customer");
      addSignup = "";
      showAddStep("details");
    });
  });
  paintAddRolePick();

  addForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    addError("");
    if (addStep === "done") {
      addForm.reset();
      setAddAccountRole("customer");
      showAddStep("details");
      return;
    }
    let role = addAccountRole();
    if (addStep === "details" && role !== "admin") {
      const pickedBefore = role;
      role = preferProductRoleForSignup(field("email").value, role);
      if (pickedBefore !== role) {
        notify("This email already has a ParkPe customer. PaySwap retailer is selected.");
      }
    }
    if (addStep === "details" && role === "admin") {
      const email = field("email").value;
      const created = await call("/api/auth/desk/accounts", {
        email,
        password: field("password").value,
        role: "admin",
      });
      if (!created.ok) return addError(created.data.error || "Could not add the admin.");
      return finishAddAccount(email, "admin");
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
        return finishAddAccount(field("email").value, role);
      }
      showAddStep("aadhaar");
      return;
    }
    if (addStep === "aadhaar") {
      const sent = await call("/api/auth/signup/aadhaar", { signup_id: addSignup });
      if (!sent.ok || !sent.data.url) return addError(sent.data.error || "Verification did not succeed.");
      const link = addForm.querySelector("[data-add-link]");
      link.hidden = false;
      link.textContent = sent.data.url;
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
    if (addStep === "pan") {
      const checked = await call("/api/auth/signup/pan", {
        signup_id: addSignup,
        pan: field("pan").value,
        name: field("pan_name").value,
      });
      if (!checked.ok || !checked.data.business_required) return addError(checked.data.error || "Verification did not succeed.");
      showAddStep("business");
      return;
    }
    if (addStep === "business") {
      if (field("location_source").value !== "desk") {
        return addError("Capture this desk's location before continuing.");
      }
      const opened = await call("/api/auth/signup/business", {
        signup_id: addSignup,
        gstin: field("gstin").value,
        udyam: field("udyam").value,
        outlet_name: field("outlet_name").value,
        lat: field("lat").value,
        lng: field("lng").value,
        location_source: "desk",
      });
      if (!opened.ok || !opened.data.account_ready) return addError(opened.data.error || "Business verification did not succeed.");
      const note = addForm.querySelector("[data-add-review]");
      if (note) {
        note.textContent = (opened.data.legal_name || "The business") + " matched GST and Udyam. Sign-in stays closed until you approve.";
      }
      showAddStep("review");
      return;
    }
    const reviewed = await call("/api/auth/desk/business-review", {
      email: field("email").value,
      decision: "approve",
    });
    if (!reviewed.ok) return addError(reviewed.data.error || "Could not approve the outlet.");
    return finishAddAccount(field("email").value, "retailer");
  });

  document.querySelector("[data-add-locate]")?.addEventListener("click", () => {
    captureDeskLocation(field("lat"), field("lng"), field("location_source"), addError);
  });

  Promise.all([call("/api/auth/me"), call("/api/auth/setup")]).then(([me, setup]) => {
    const create = document.querySelector("[data-show='register']");
    if (setup.data.signup_open) create.hidden = false;
    if (me.ok && me.data.role === ROLE) enter(me.data);
    else if (me.status === 403 && me.data.mfa_setup_required && me.data.role === ROLE) show("enroll");
    else show("login");
  });
})();
