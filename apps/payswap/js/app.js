/* PaySwap counter for apps/payswap/index.html.

   Sign-in, MFA, profile, and sessions go through apps/payswap/js/session.js
   (role retailer, port 4600). Retailer entitlements, wallet, PG, BBPS, and
   transactions go through apps/payswap/js/hub.js (/api/v1/payswap/*).
*/
(function () {
  const view = document.getElementById("view");
  const crumb = document.getElementById("crumb");
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.querySelector(".backdrop");
  const menuBtn = document.querySelector(".menu-btn");

  const esc = window.Payswap.esc;
  const rupee = window.Payswap.rupee;

  function httpUrl(value) {
    const s = String(value || "").trim();
    return /^https?:\/\//i.test(s) ? s : "";
  }

  function slipRowEl(label, value) {
    const row = document.createElement("div");
    row.className = "slip-row";
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = String(value == null ? "" : value);
    row.append(span, strong);
    return row;
  }

  /* PG top-up panel: DOM only so API fields never hit innerHTML. */
  function renderPgWalletBox(box, { orderId, amount, checkoutUrl, linkLabel, verifyId }) {
    if (!box) return;
    box.replaceChildren();
    const kicker = document.createElement("p");
    kicker.className = "kicker";
    kicker.textContent = "PG Wallet Top-up";
    box.append(kicker, slipRowEl("Order ID", orderId), slipRowEl("Amount", amount));
    const url = httpUrl(checkoutUrl);
    if (url) {
      const a = document.createElement("a");
      a.className = "btn yellow";
      a.href = url;
      a.rel = "noopener";
      a.textContent = linkLabel || "Pay Now";
      box.append(a);
    }
    const btn = document.createElement("button");
    btn.className = "btn";
    btn.type = "button";
    btn.dataset.pgVerify = String(verifyId || orderId || "");
    btn.textContent = "Verify payment";
    box.append(btn);
  }

  function renderPgCheckoutReceipt(box, cardHtml, { checkoutUrl, verifyId }) {
    if (!box) return;
    box.replaceChildren();
    const tpl = document.createElement("template");
    tpl.innerHTML = String(cardHtml || "");
    box.append(tpl.content);
    const actions = document.createElement("div");
    actions.className = "slip-actions";
    const url = httpUrl(checkoutUrl);
    if (url) {
      const a = document.createElement("a");
      a.className = "btn yellow block";
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = "Open PG Checkout";
      actions.append(a);
    }
    const btn = document.createElement("button");
    btn.className = "btn block";
    btn.type = "button";
    btn.dataset.pgVerify = String(verifyId || "");
    btn.textContent = "Verify & Execute BBPS";
    actions.append(btn);
    box.append(actions);
  }

  /* PayU Hosted Checkout: real browser form POST (not fetch) to PayU _payment. */
  function submitPayuHostedCheckout(payload) {
    const action = payload && payload.action;
    const params = payload && payload.params;
    if (!action || !params || typeof params !== "object" || !params.hash) return false;
    const form = document.createElement("form");
    form.method = "POST";
    form.action = action;
    form.style.display = "none";
    Object.keys(params).forEach((name) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = String(params[name] == null ? "" : params[name]);
      form.appendChild(input);
    });
    document.body.appendChild(form);
    form.submit();
    return true;
  }

  /* Cashfree: prefer hosted payment-link URL (full redirect). Fallback to JS SDK session. */
  function openCashfreeCheckout(payload) {
    const checkoutUrl = payload && String(payload.checkout_url || "").trim();
    if (checkoutUrl && /^https:\/\//i.test(checkoutUrl)) {
      window.location.assign(checkoutUrl);
      return true;
    }
    const sessionId = payload && String(payload.payment_session_id || "").trim();
    if (!sessionId) return false;
    if (typeof globalThis.Cashfree !== "function") return false;
    const mode = String(payload.cashfree_mode || "sandbox").toLowerCase() === "production" ? "production" : "sandbox";
    try {
      const cashfree = globalThis.Cashfree({ mode });
      const result = cashfree.checkout({ paymentSessionId: sessionId, redirectTarget: "_self" });
      if (result && typeof result.then === "function") {
        result.then((out) => {
          if (out && out.error) {
            console.warn("Cashfree checkout", out.error.message || out.error);
          }
        }).catch(() => {});
      }
      return true;
    } catch (_err) {
      return false;
    }
  }

  function hashRouteParts() {
    const raw = (location.hash || "").replace(/^#/, "");
    const q = raw.indexOf("?");
    if (q < 0) return { page: raw.trim(), params: new URLSearchParams() };
    return { page: raw.slice(0, q).trim(), params: new URLSearchParams(raw.slice(q + 1)) };
  }

  function playPgTone(ok) {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      const now = ctx.currentTime;
      const master = ctx.createGain();
      master.gain.setValueAtTime(0.0001, now);
      master.connect(ctx.destination);
      if (ok) {
        master.gain.exponentialRampToValueAtTime(0.09, now + 0.02);
        master.gain.exponentialRampToValueAtTime(0.0001, now + 0.55);
        [523.25, 659.25, 783.99].forEach((freq, i) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = "sine";
          osc.frequency.value = freq;
          const t0 = now + i * 0.09;
          gain.gain.setValueAtTime(0.0001, t0);
          gain.gain.exponentialRampToValueAtTime(0.12, t0 + 0.02);
          gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.28);
          osc.connect(gain);
          gain.connect(master);
          osc.start(t0);
          osc.stop(t0 + 0.3);
        });
        window.setTimeout(() => ctx.close().catch(() => {}), 700);
      } else {
        master.gain.exponentialRampToValueAtTime(0.08, now + 0.02);
        master.gain.exponentialRampToValueAtTime(0.0001, now + 0.4);
        const osc = ctx.createOscillator();
        osc.type = "triangle";
        osc.frequency.setValueAtTime(260, now);
        osc.frequency.exponentialRampToValueAtTime(120, now + 0.34);
        osc.connect(master);
        osc.start(now);
        osc.stop(now + 0.38);
        osc.onended = () => ctx.close().catch(() => {});
      }
    } catch {
      /* autoplay may be blocked after gateway redirect */
    }
  }

  function dismissPgOutcome() {
    document.getElementById("pg-outcome")?.remove();
  }

  /* PaySwap PG return UX — not Bharat Connect / BBPS mogo. */
  function showPgOutcome({ ok = false, amount = "", orderId = "", detail = "" } = {}) {
    dismissPgOutcome();
    dismissBbpsCelebration();
    playPgTone(!!ok);
    const host = document.createElement("div");
    host.id = "pg-outcome";
    host.className = `pg-outcome ${ok ? "is-ok" : "is-fail"}`;
    host.setAttribute("role", "dialog");
    host.setAttribute("aria-modal", "true");
    host.setAttribute("aria-label", ok ? "Payment successful" : "Payment failed");
    const title = ok ? "Payment successful" : "Payment failed";
    const meta = detail || (ok ? "Wallet credit is on the way." : "No money was taken for this attempt.");
    const amountLine = amount ? `<p class="pg-outcome-amount">${esc(rupee(amount))}</p>` : "";
    const refLine = orderId ? `<p class="pg-outcome-ref">Order ${esc(orderId)}</p>` : "";
    host.innerHTML = `
      <div class="pg-outcome-card">
        <div class="pg-outcome-burst" aria-hidden="true"></div>
        <div class="pg-outcome-mark" aria-hidden="true"><span class="mi">${ok ? "check" : "close"}</span></div>
        <p class="pg-outcome-kicker">PaySwap</p>
        <h2>${title}</h2>
        ${amountLine}
        <p class="pg-outcome-meta">${esc(meta)}</p>
        ${refLine}
        <button type="button" class="btn ${ok ? "yellow" : ""} block" data-pg-outcome-close>Continue</button>
      </div>`;
    document.body.appendChild(host);
    requestAnimationFrame(() => host.classList.add("is-on"));
    host.querySelector("[data-pg-outcome-close]")?.addEventListener("click", dismissPgOutcome);
    host.addEventListener("click", (event) => {
      if (event.target === host) dismissPgOutcome();
    });
    window.setTimeout(dismissPgOutcome, ok ? 5200 : 6000);
  }

  function applyPgReturnResult(res, { fallbackOk = null, orderId = "" } = {}) {
    if (res && res.ok && res.data && res.data.wallet) updateHeaderWallet(res.data.wallet);
    const status = String((res && res.data && res.data.status) || "").toLowerCase();
    const state = String((res && res.data && res.data.state) || "").toLowerCase();
    const paid = status === "paid" || state === "success";
    const failed = status === "failed" || state === "failed" || state === "failure";
    const ok = paid ? true : failed ? false : fallbackOk;
    if (ok == null) return;
    const amount = (res && res.data && (res.data.amount || res.data.total_amount)) || "";
    const oid = orderId || (res && res.data && (res.data.pg_order_id || res.data.order_id)) || "";
    showPgOutcome({
      ok,
      amount,
      orderId: oid,
      detail: ok
        ? state === "success"
          ? "Bill payment settled."
          : "Top-up settled on your wallet."
        : (res && res.error) || "Gateway reported a failed or cancelled payment.",
    });
    const page = hashRouteParts().page || "wallet";
    if (page === "wallet" || !page) initWalletScreen();
  }

  function resumeCashfreeReturn() {
    const params = new URLSearchParams(location.search || "");
    const orderId = (params.get("cf_order_id") || params.get("order_id") || params.get("link_id") || "").trim();
    if (!orderId || !globalThis.PayswapHub) return;
    // Clear return params so refresh does not re-verify forever.
    try {
      const clean = location.pathname + (location.hash || "#wallet");
      history.replaceState(null, "", clean);
    } catch (_err) {}
    globalThis.PayswapHub.verifyPgOrder(orderId, crypto.randomUUID()).then((res) => {
      applyPgReturnResult(res, { orderId });
    });
  }

  const PAYU_RETURN_KEY = "payswap-payu-return";

  /* Must run before route()/show() — show() used to replace #wallet?payu=… with #wallet. */
  function capturePayuReturn() {
    const { page, params } = hashRouteParts();
    const flag = String(params.get("payu") || "").trim().toLowerCase();
    if (flag !== "ok" && flag !== "fail") return null;
    const orderId = String(params.get("order_id") || "").trim();
    try {
      history.replaceState(null, "", `${location.pathname}#${page || "wallet"}`);
    } catch (_err) {}
    return { ok: flag === "ok", orderId, page: page || "wallet" };
  }

  function stashPayuReturn(data) {
    if (!data) return;
    try {
      sessionStorage.setItem(PAYU_RETURN_KEY, JSON.stringify(data));
    } catch (_err) {}
  }

  function takeStashedPayuReturn() {
    try {
      const raw = sessionStorage.getItem(PAYU_RETURN_KEY);
      if (!raw) return null;
      sessionStorage.removeItem(PAYU_RETURN_KEY);
      return JSON.parse(raw);
    } catch (_err) {
      return null;
    }
  }

  function resumePayuReturn(captured) {
    if (!captured) return;
    const { ok: fallbackOk, orderId } = captured;
    showPgOutcome({
      ok: fallbackOk,
      orderId: orderId || "",
      detail: fallbackOk ? "Payment completed on PayU." : "Payment did not complete on PayU.",
    });
    if (!orderId || !globalThis.PayswapHub || !appState.user) return;
    globalThis.PayswapHub.verifyPgOrder(orderId, crypto.randomUUID())
      .then((res) => applyPgReturnResult(res, { fallbackOk, orderId }))
      .catch(() => {});
  }

  const appState = {
    user: null,
    entitlements: null,
    wallet: null,
    walletLedger: [],
    ledgerDirFilter: "all",
    pgConfigured: false,
    pgProvider: "both",
    transactions: [],
    pgOrders: [],
    txnServiceFilter: "all",
    txnStateFilter: "all",
    txnQuery: "",
    activeReceiptRef: "",
    txnFeedback: null,
  };

  const bbpsState = {
    category: "",
    categories: [],
    showAllCategories: false,
    operator: null,
    operators: [],
    lastReference: "",
    lastReceipt: null,
    lastReceiptData: null,
    searchTimer: 0,
    configured: false,
    loading: false,
    circles: [],
    plans: [],
    planCategory: "all",
  };
  let txnSearchTimer = 0;
  let coreStateFetchedAt = 0;
  const CORE_STATE_TTL_MS = 45000;

  function isPrepaidLike(op) {
    const cat = String((op && op.category) || bbpsState.category || "").toUpperCase();
    return cat === "PREPAID" || cat === "DTH";
  }

  /* Bharat Connect brand journey (Brand Identity Guidelines + NPCI/2023-24/BBPS/012,
     rebranded assets from https://www.bharat-connect.com/as/brand-centre/):
     Stage-1 entry → B mnemonic
     Stage-2 biller / fetch / pay / txn status → Bharat Connect logo (top-right)
     Stage-3 success confirmation + receipt only → B Assured
       online receipt: Assured top-left; print/paper: Assured top-right
     Never put Assured on journey screens; never put both logos as co-equals. */
  const BBPS_BRAND = {
    logo: "assets/bbps/bharat-connect-logo.svg",
    mnemonic: "assets/bbps/b-mnemonic.svg",
    assured: "assets/bbps/b-assured.svg",
    mogo: "assets/bbps/mogo.mp3",
    ouLogo: "assets/payswap-logo.svg",
    verifyUrl: "https://www.bharat-connect.com/",
  };
  let bbpsMogoAudio = null;

  const BBPS_CAT_ICONS = {
    ELECTRICITY: "bolt",
    FASTAG: "directions_car",
    PREPAID: "smartphone",
    MOBILE_POSTPAID: "phone_android",
    DTH: "tv",
    GAS: "local_fire_department",
    LPG_BOOKING: "propane_tank",
    WATER: "water_drop",
    BROADBAND_POSTPAID: "wifi",
    BROADBAND: "wifi",
    CREDIT_CARD: "credit_card",
    LOAN_REPAYMENT: "account_balance",
    EMI_PAYMENT: "payments",
    INSURANCE: "shield",
    HEALTH_INSURANCE: "health_and_safety",
    MUNICIPAL_TAXES: "location_city",
    CABLE_TV: "cable",
    LANDLINE: "call",
    EDUCATION: "school",
    HOUSING_SOCIETY: "apartment",
    SUBSCRIPTION: "subscriptions",
    DONATION: "volunteer_activism",
    AGENT_COLLECTION: "badge",
    VOUCHER: "confirmation_number",
    CLUBS_AND_ASSOCIATIONS: "groups",
    HOSPITAL_PATHOLOGY: "local_hospital",
  };

  function compactCount(n) {
    const num = Number(n || 0);
    if (num >= 1000) return (num / 1000).toFixed(num >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k";
    return String(num);
  }

  function attemptKey(name) {
    const existing = sessionStorage.getItem(name);
    if (existing) return existing;
    const key = crypto.randomUUID();
    sessionStorage.setItem(name, key);
    return key;
  }

  function clearError(input) {
    input.removeAttribute("aria-invalid");
    const message = input.closest(".field")?.querySelector(".error");
    if (message) message.remove();
  }

  function setError(input, message) {
    const field = input.closest(".field") || input.parentElement;
    clearError(input);
    input.setAttribute("aria-invalid", "true");
    const node = document.createElement("span");
    node.className = "error";
    node.textContent = message;
    field.append(node);
    input.focus();
  }

  function markChips(group, value) {
    group.querySelectorAll("[data-amt]").forEach((chip) => chip.classList.toggle("is-on", chip.dataset.amt === String(value)));
  }

  function formatDateTime(iso) {
    if (!iso) return "—";
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return String(iso);
    return dt.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function statePillClass(state) {
    if (state === "success" || state === "approved" || state === "paid" || state === "credited") return "ok";
    if (state === "failed" || state === "rejected" || state === "frozen") return "bad";
    return "wait";
  }

  function statusLabel(state) {
    if (state === "success" || state === "approved" || state === "paid") return "Success";
    if (state === "credited") return "Credited";
    if (state === "failed" || state === "rejected") return "Failed";
    if (state === "pending" || state === "created") return "Pending";
    return state ? String(state) : "—";
  }

  function updateHeaderWallet(wallet) {
    if (wallet) appState.wallet = wallet;
    const w = appState.wallet;
    const balEl = document.querySelector("[data-header-balance]");
    if (balEl && w) balEl.textContent = rupee(w.available);
    const chip = document.getElementById("header-wallet-chip");
    if (chip && w) {
      chip.title = `Available ${rupee(w.available)} · Held ${rupee(w.held)} · Status ${w.status}`;
    }
    const bbpsChip = document.querySelector("[data-bbps-wallet-chip]");
    if (bbpsChip && w) bbpsChip.textContent = rupee(w.available);
  }

  function applyEntitlements() {
    const ent = appState.entitlements;
    const enabled = ent && Array.isArray(ent.enabled_services) ? ent.enabled_services : null;
    if (!enabled) return;
    let visibleServiceItems = 0;
    document.querySelectorAll(".nav[data-service]").forEach((link) => {
      const svc = link.dataset.service;
      let on = enabled.includes(svc);
      if (svc === "bbps_bulk") {
        on = enabled.includes("bbps") && Boolean(ent.bbps_bulk_enabled);
      }
      link.hidden = !on;
      if (["bbps", "bbps_bulk", "recharge", "vouchers", "dmt", "aeps"].includes(svc) && on) {
        visibleServiceItems += 1;
      }
    });
    const svcHeader = document.querySelector("[data-nav-group='services']");
    if (svcHeader) svcHeader.hidden = visibleServiceItems === 0;
    const walletChip = document.getElementById("header-wallet-chip");
    if (walletChip) walletChip.hidden = !enabled.includes("wallet");
  }

  async function refreshCoreState(options = {}) {
    if (!globalThis.PayswapHub) return;
    const force = Boolean(options && options.force);
    const now = Date.now();
    if (
      !force &&
      appState.entitlements &&
      appState.wallet &&
      coreStateFetchedAt &&
      now - coreStateFetchedAt < CORE_STATE_TTL_MS
    ) {
      applyEntitlements();
      updateHeaderWallet(appState.wallet);
      return;
    }
    const [entRes, walletRes] = await Promise.all([
      globalThis.PayswapHub.entitlements(),
      globalThis.PayswapHub.wallet().catch(() => ({ ok: false })),
    ]);
    if (entRes.ok && entRes.data) {
      appState.entitlements = entRes.data;
      applyEntitlements();
    } else if (entRes.status === 401 || entRes.status === 403) {
      await handleSessionRejection(entRes);
    }
    if (walletRes && walletRes.ok && walletRes.data) {
      appState.wallet = walletRes.data.wallet;
      appState.pgConfigured = Boolean(walletRes.data.pg_configured);
      updateHeaderWallet(walletRes.data.wallet);
    }
    if ((entRes.ok && entRes.data) || (walletRes && walletRes.ok)) {
      coreStateFetchedAt = Date.now();
    }
  }

  function clearScreenTimers(nextKey) {
    if (nextKey !== "bulk-bills") {
      clearTimeout(bulkState.pollTimer);
      bulkState.pollTimer = null;
      clearTimeout(bulkState.billerSearchTimer);
      bulkState.billerSearchTimer = 0;
    }
    if (nextKey !== "bills") {
      clearTimeout(bbpsState.searchTimer);
      clearTimeout(bbpsPlanTimer);
      bbpsState.searchTimer = 0;
      bbpsPlanTimer = 0;
    }
    if (nextKey !== "transactions") {
      clearTimeout(txnSearchTimer);
      txnSearchTimer = 0;
    }
  }

  function show(name) {
    const allowed = appState.entitlements ? appState.entitlements.enabled_services : null;
    const requested = String(name || "").split("?")[0].split("/")[0] || "home";
    const key = window.Payswap.mount(view, requested, allowed, appState.entitlements);
    clearScreenTimers(key);
    const title = window.Payswap.titles[key] || "Home";
    crumb.textContent = title;
    document.title = `${title} · PaySwap`;
    document.querySelectorAll(".nav").forEach((link) => link.classList.toggle("is-on", link.dataset.view === key));
    sidebar.classList.remove("is-open");
    backdrop.hidden = true;
    menuBtn.setAttribute("aria-expanded", "false");
    // Keep the user on the same screen across refresh; only rewrite hash when it drifted.
    // Compare page only — keep #wallet?payu=… until capturePayuReturn runs.
    if (hashRouteParts().page !== key) history.replaceState(null, "", `#${key}`);
    try {
      sessionStorage.setItem("payswap-route", key);
    } catch (_err) {
      /* ignore */
    }

    if (key === "home") initHomeScreen();
    else if (key === "bills") initBbpsScreen();
    else if (key === "bulk-bills") initBulkBillsScreen();
    else if (key === "wallet") initWalletScreen();
    else if (key === "transactions") initTransactionsScreen();
    else if (key === "profile") initProfileScreen();
  }

  const bulkState = {
    batchId: "",
    due: "all",
    fetch: "all",
    q: "",
    pollTimer: null,
    category: "",
    categories: [],
    operators: [],
    /** @type {Record<string, { op: string, biller_id: string, name: string, category: string, count: number }>} */
    selected: {},
    billerSearchTimer: 0,
  };

  function bulkSelectedList() {
    return Object.values(bulkState.selected || {});
  }

  function bulkSelectedTotalRows() {
    return bulkSelectedList().reduce((sum, item) => sum + Math.max(1, Number(item.count) || 1), 0);
  }

  function setBulkStatus(msg, tone) {
    const el = view.querySelector("[data-bulk-status]");
    if (!el) return;
    el.hidden = !msg;
    el.textContent = msg || "";
    el.className = `preview-result bulk-status${tone ? ` is-${tone}` : ""}`;
    if (msg) {
      try {
        el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      } catch (_err) {
        /* ignore */
      }
    }
  }

  function persistBulkSelected() {
    try {
      sessionStorage.setItem("payswap-bulk-selected", JSON.stringify(bulkState.selected || {}));
    } catch (_err) {
      /* ignore */
    }
  }

  function restoreBulkSelected() {
    try {
      const raw = sessionStorage.getItem("payswap-bulk-selected");
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        bulkState.selected = parsed;
      }
    } catch (_err) {
      /* ignore */
    }
  }

  function paintBulkBatch(batch) {
    if (!batch) return;
    const set = (sel, text) => {
      const el = view.querySelector(sel);
      if (el) el.textContent = text;
    };
    set("[data-bulk-stat-rows]", String(batch.row_count || 0));
    const billerLabel = batch.biller_name || batch.operator_id || "";
    set(
      "[data-bulk-stat-file]",
      billerLabel
        ? `${billerLabel} · ${batch.source_filename || batch.batch_id || ""}`
        : batch.source_filename || batch.batch_id || "—",
    );
    set("[data-bulk-stat-fetch]", String(batch.fetch_ok || 0));
    set("[data-bulk-stat-fetch-fail]", `${batch.fetch_fail || 0} failed`);
    set("[data-bulk-stat-due]", rupee(batch.fetch_due_total || batch.ready_total || "0"));
    set("[data-bulk-stat-wallet]", `Wallet ${rupee(batch.wallet_available || "0")}`);
    set("[data-bulk-stat-paid]", String(batch.pay_ok || 0));
    set("[data-bulk-stat-status]", `${batch.status || "—"} · pipe ${batch.pipe || "—"}`);
  }

  function syncBulkBillerActions() {
    const selected = bulkSelectedList();
    const tmpl = view.querySelector("[data-bulk-template]");
    const file = view.querySelector("[data-bulk-file]");
    const uploadLabel = view.querySelector("[data-bulk-upload-label]");
    const picked = view.querySelector("[data-bulk-biller-picked]");
    const panel = view.querySelector("[data-bulk-selected]");
    const totalEl = view.querySelector("[data-bulk-selected-total]");
    const ready = selected.length > 0 && bulkSelectedTotalRows() > 0;
    if (tmpl) tmpl.disabled = !ready;
    // Sheet already has biller_id per row — upload must stay clickable even if selection cleared.
    if (file) file.disabled = false;
    if (uploadLabel) uploadLabel.classList.remove("is-disabled");
    if (picked) {
      picked.textContent = ready
        ? `${selected.length} biller${selected.length === 1 ? "" : "s"} · ${bulkSelectedTotalRows()} bill rows`
        : "No billers selected yet.";
    }
    if (panel) panel.hidden = !selected.length;
    if (totalEl) {
      totalEl.textContent = ready
        ? `${bulkSelectedTotalRows()} rows will be in the download (max 500).`
        : "0 rows will be in the download.";
    }
  }

  function paintBulkSelectedRows() {
    const box = view.querySelector("[data-bulk-selected-rows]");
    if (!box) return;
    const selected = bulkSelectedList();
    if (!selected.length) {
      box.innerHTML = "";
      syncBulkBillerActions();
      return;
    }
    box.innerHTML =
      `<div class="bulk-selected-head" aria-hidden="true"><span>Biller</span><span>Bills</span><span></span></div>` +
      selected
        .map(
          (item) => `<div class="bulk-selected-row" data-bulk-selected-op="${esc(item.op)}">
          <div>
            <strong>${esc(item.name || item.op)}</strong>
            <small>${esc(item.op)}${item.category ? ` · ${esc(item.category)}` : ""}</small>
          </div>
          <label class="field">
            <span class="bulk-count-label">Bills</span>
            <input type="number" min="1" max="500" step="1" value="${esc(String(item.count || 1))}" data-bulk-count-op="${esc(item.op)}" aria-label="How many bills for ${esc(item.name || item.op)}" />
          </label>
          <button type="button" class="btn-icon" data-bulk-remove-op="${esc(item.op)}" aria-label="Remove ${esc(item.name || item.op)}"><span class="mi">close</span></button>
        </div>`,
        )
        .join("");
    syncBulkBillerActions();
  }

  function paintBulkBillerList(operators) {
    const box = view.querySelector("[data-bulk-biller-list]");
    if (!box) return;
    const rows = Array.isArray(operators) ? operators : [];
    if (!rows.length) {
      box.innerHTML = `<p class="hint">No billers in this category. Try another category or search.</p>`;
      return;
    }
    box.innerHTML = rows
      .map((op) => {
        const id = String(op.op || op.biller_id || "");
        const on = Boolean(bulkState.selected[id]) ? " is-on" : "";
        return `<button type="button" class="bulk-biller-row${on}" role="option" data-bulk-pick-op="${esc(id)}" aria-selected="${on ? "true" : "false"}">
          <span><strong>${esc(op.name || id)}</strong><small>${esc(id)}${op.category ? ` · ${esc(op.category)}` : ""}</small></span>
          <span class="mi" aria-hidden="true">${on ? "check_circle" : "add_circle"}</span>
        </button>`;
      })
      .join("");
  }

  async function loadBulkBillerCatalogue({ category = "", q = "" } = {}) {
    const box = view.querySelector("[data-bulk-biller-list]");
    if (!globalThis.PayswapHub) return;
    if (box) box.innerHTML = `<p class="hint">Loading billers…</p>`;
    const res = await globalThis.PayswapHub.bbpsOperators({
      category: category || undefined,
      q: q || undefined,
      limit: 120,
    });
    if (!res.ok) {
      if (box) box.innerHTML = `<p class="hint">${esc(res.error || "Could not load billers.")}</p>`;
      return;
    }
    const cats = res.data.categories || [];
    if (cats.length) {
      bulkState.categories = cats;
      const select = view.querySelector("[data-bulk-category]");
      if (select && select.options.length <= 1) {
        select.innerHTML =
          `<option value="">All categories</option>` +
          cats.map((c) => `<option value="${esc(c.id || c.name || "")}">${esc(c.name || c.id || "")}</option>`).join("");
        if (bulkState.category) select.value = bulkState.category;
      }
    }
    bulkState.operators = res.data.operators || [];
    paintBulkBillerList(bulkState.operators);
  }

  function paintBulkRows(rows) {
    const table = view.querySelector("[data-bulk-table]");
    const empty = view.querySelector("[data-bulk-empty]");
    const actions = view.querySelector("[data-bulk-actions]");
    if (!table) return;
    if (!rows.length) {
      table.hidden = true;
      if (empty) empty.hidden = false;
      if (actions) actions.hidden = !bulkState.batchId;
      table.innerHTML = "";
      return;
    }
    if (empty) empty.hidden = true;
    table.hidden = false;
    if (actions) actions.hidden = false;
    table.innerHTML = `<table class="desk-table bulk-table"><thead><tr>
      <th>#</th><th>Biller</th><th>Account</th><th>Due</th><th>Fetch</th><th>Pay</th><th>Ref</th><th>Error</th>
    </tr></thead><tbody>${rows
      .map(
        (r) => `<tr>
      <td>${esc(String(r.row_no))}</td>
      <td><strong>${esc(r.biller_name || r.operator_id || "—")}</strong><small>${esc(r.category || "")}</small></td>
      <td class="mono">${esc(r.account_mask || "—")}</td>
      <td>${esc(rupee(r.due_amount || "0"))}<small>${esc(r.due_date || r.due_bucket || "")}</small></td>
      <td><span class="pill">${esc(r.fetch_state || "")}</span></td>
      <td><span class="pill">${esc(r.pay_state || "")}</span></td>
      <td class="mono">${r.bbps_reference ? `<a href="#transactions">${esc(r.bbps_reference)}</a>` : "—"}</td>
      <td>${esc(r.fetch_error || r.pay_error || "")}</td>
    </tr>`,
      )
      .join("")}</tbody></table>`;
  }

  async function loadBulkDetail(batchId) {
    if (!globalThis.PayswapHub || !batchId) return;
    bulkState.batchId = batchId;
    const params = { limit: 200 };
    if (bulkState.fetch !== "all") params.fetch_state = bulkState.fetch === "ok" ? "ok" : bulkState.fetch;
    if (bulkState.due !== "all") params.due_bucket = bulkState.due;
    if (bulkState.q) params.q = bulkState.q;
    const res = await globalThis.PayswapHub.bulkBbpsRows(batchId, params);
    if (!res.ok) {
      setBulkStatus(res.error || "Could not load batch rows.", "error");
      return;
    }
    paintBulkBatch(res.data.batch || {});
    paintBulkRows(res.data.rows || []);
    const st = (res.data.batch && res.data.batch.status) || "";
    if (["fetching", "paying"].includes(st)) {
      clearTimeout(bulkState.pollTimer);
      bulkState.pollTimer = setTimeout(() => loadBulkDetail(batchId), 2500);
    }
  }

  async function loadBulkBatchesList() {
    const box = view.querySelector("[data-bulk-batches]");
    if (!box || !globalThis.PayswapHub) return;
    const res = await globalThis.PayswapHub.bulkBbpsBatches();
    if (!res.ok) {
      box.innerHTML = `<p class="hint">${esc(res.error || "Could not load batches.")}</p>`;
      return;
    }
    const rows = res.data.batches || [];
    if (!rows.length) {
      box.innerHTML = `<p class="hint">No bulk batches yet.</p>`;
      return;
    }
    box.innerHTML = `<ul class="rows">${rows
      .map(
        (b) => `<li><button type="button" class="linkish" data-bulk-open="${esc(b.batch_id)}"><strong>${esc(b.biller_name || b.batch_id)}</strong> · ${esc(b.status)} · ${esc(String(b.row_count))} rows · ${esc(b.source_filename || b.batch_id || "")}</button></li>`,
      )
      .join("")}</ul>`;
    box.querySelectorAll("[data-bulk-open]").forEach((btn) => {
      btn.addEventListener("click", () => loadBulkDetail(btn.dataset.bulkOpen));
    });
  }

  async function initBulkBillsScreen() {
    await refreshCoreState();
    clearTimeout(bulkState.pollTimer);
    restoreBulkSelected();
    bulkState.category = "";
    paintBulkSelectedRows();
    syncBulkBillerActions();

    view.querySelector("[data-bulk-category]")?.addEventListener("change", (ev) => {
      bulkState.category = ev.target.value || "";
      const q = view.querySelector("[data-bulk-biller-q]")?.value || "";
      loadBulkBillerCatalogue({ category: bulkState.category, q });
    });
    view.querySelector("[data-bulk-biller-q]")?.addEventListener("input", (ev) => {
      clearTimeout(bulkState.billerSearchTimer);
      const q = ev.target.value.trim();
      bulkState.billerSearchTimer = setTimeout(() => {
        loadBulkBillerCatalogue({ category: bulkState.category, q });
      }, 220);
    });
    view.querySelector("[data-bulk-biller-list]")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-bulk-pick-op]");
      if (!btn) return;
      const id = btn.dataset.bulkPickOp || "";
      if (!id) return;
      if (bulkState.selected[id]) {
        delete bulkState.selected[id];
      } else {
        const op = (bulkState.operators || []).find((row) => String(row.op || row.biller_id || "") === id);
        if (!op) return;
        bulkState.selected[id] = {
          op: String(op.op || id),
          biller_id: String(op.biller_id || op.op || id),
          name: String(op.name || id),
          category: String(op.category || ""),
          count: 1,
        };
      }
      paintBulkBillerList(bulkState.operators);
      paintBulkSelectedRows();
      persistBulkSelected();
      const n = bulkSelectedList().length;
      setBulkStatus(
        n
          ? `${n} biller${n === 1 ? "" : "s"} selected · set bill counts, then Download sheet.`
          : "",
        n ? "ok" : "",
      );
    });
    view.querySelector("[data-bulk-selected]")?.addEventListener("input", (ev) => {
      const input = ev.target.closest("[data-bulk-count-op]");
      if (!input) return;
      const id = input.dataset.bulkCountOp || "";
      if (!bulkState.selected[id]) return;
      let count = parseInt(input.value, 10);
      if (!Number.isFinite(count) || count < 1) count = 1;
      if (count > 500) count = 500;
      bulkState.selected[id].count = count;
      persistBulkSelected();
      syncBulkBillerActions();
    });
    view.querySelector("[data-bulk-selected]")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-bulk-remove-op]");
      if (!btn) return;
      const id = btn.dataset.bulkRemoveOp || "";
      delete bulkState.selected[id];
      persistBulkSelected();
      paintBulkBillerList(bulkState.operators);
      paintBulkSelectedRows();
    });

    view.querySelector("[data-bulk-template]")?.addEventListener("click", async (ev) => {
      ev.preventDefault();
      const selected = bulkSelectedList();
      if (!selected.length) return setBulkStatus("Select at least one biller first.", "error");
      const billers = selected.map((item) => ({
        op: item.op,
        biller_id: item.biller_id,
        count: Math.max(1, Math.min(500, Number(item.count) || 1)),
      }));
      const total = billers.reduce((sum, item) => sum + item.count, 0);
      if (total > 500) return setBulkStatus("Total bill rows cannot exceed 500.", "error");
      const btn = view.querySelector("[data-bulk-template]");
      if (btn) btn.disabled = true;
      setBulkStatus("Downloading sheet…", "");
      try {
        const res = await globalThis.PayswapHub.downloadBulkBbpsTemplate({ billers });
        if (!res.ok) {
          setBulkStatus(res.error || "Sheet download failed.", "error");
          return;
        }
        setBulkStatus(
          `Sheet ready · ${billers.length} biller${billers.length === 1 ? "" : "s"} · ${total} rows. Fill consumer numbers, then upload.`,
          "ok",
        );
      } catch (err) {
        setBulkStatus((err && err.message) || "Sheet download failed.", "error");
      } finally {
        syncBulkBillerActions();
      }
    });
    view.querySelector("[data-bulk-file]")?.addEventListener("change", async (ev) => {
      const file = ev.target.files && ev.target.files[0];
      if (!file) return;
      setBulkStatus("Uploading…", "");
      try {
        // Sheet carries biller_id per row; do not lock to a single operator.
        const res = await globalThis.PayswapHub.uploadBulkBbps(file, {});
        ev.target.value = "";
        if (!res.ok) {
          setBulkStatus(res.error || "Upload failed. Fill consumer_number in the sheet and try again.", "error");
          return;
        }
        const rows = Number(res.data.row_count || 0);
        const label = res.data.biller_name || res.data.source_filename || res.data.batch_id || "batch";
        setBulkStatus(
          rows
            ? `Uploaded ${rows} row${rows === 1 ? "" : "s"} · ${label}.`
            : `Batch ${res.data.batch_id || ""} uploaded · ${label}.`,
          "ok",
        );
        paintBulkBatch(res.data);
        await loadBulkDetail(res.data.batch_id);
        loadBulkBatchesList();
      } catch (err) {
        ev.target.value = "";
        setBulkStatus((err && err.message) || "Upload failed.", "error");
      }
    });
    view.querySelectorAll("[data-bulk-due]").forEach((btn) => {
      btn.addEventListener("click", () => {
        bulkState.due = btn.dataset.bulkDue || "all";
        view.querySelectorAll("[data-bulk-due]").forEach((n) => n.classList.toggle("is-on", n === btn));
        if (bulkState.batchId) loadBulkDetail(bulkState.batchId);
      });
    });
    view.querySelectorAll("[data-bulk-fetch]").forEach((btn) => {
      btn.addEventListener("click", () => {
        bulkState.fetch = btn.dataset.bulkFetch || "all";
        view.querySelectorAll("[data-bulk-fetch]").forEach((n) => n.classList.toggle("is-on", n === btn));
        if (bulkState.batchId) loadBulkDetail(bulkState.batchId);
      });
    });
    view.querySelector("[data-bulk-q]")?.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      bulkState.q = ev.target.value || "";
      if (bulkState.batchId) loadBulkDetail(bulkState.batchId);
    });
    view.querySelector("[data-bulk-refetch]")?.addEventListener("click", async () => {
      if (!bulkState.batchId) return;
      const res = await globalThis.PayswapHub.refetchBulkBbps(bulkState.batchId);
      if (!res.ok) return setBulkStatus(res.error || "Re-fetch failed.", "error");
      setBulkStatus("Re-fetch queued.", "ok");
      loadBulkDetail(bulkState.batchId);
    });
    view.querySelector("[data-bulk-export]")?.addEventListener("click", async () => {
      if (!bulkState.batchId) return;
      setBulkStatus("Exporting CSV…", "");
      const res = await globalThis.PayswapHub.downloadBulkBbpsExport(bulkState.batchId);
      if (!res.ok) return setBulkStatus(res.error || "Export failed.", "error");
      setBulkStatus("CSV exported.", "ok");
    });
    view.querySelector("[data-bulk-cancel]")?.addEventListener("click", async () => {
      if (!bulkState.batchId) return;
      const res = await globalThis.PayswapHub.cancelBulkBbps(bulkState.batchId);
      if (!res.ok) return setBulkStatus(res.error || "Cancel failed.", "error");
      setBulkStatus("Batch cancelled.", "ok");
      loadBulkDetail(bulkState.batchId);
      loadBulkBatchesList();
    });
    view.querySelector("[data-bulk-proceed]")?.addEventListener("click", async () => {
      if (!bulkState.batchId) return;
      const pin = view.querySelector("[data-bulk-pin]")?.value || "";
      if (!pin) return setBulkStatus("Enter wallet PIN to proceed.", "error");
      setBulkStatus("Paying ready rows…", "");
      const res = await globalThis.PayswapHub.proceedBulkBbps(bulkState.batchId, { wallet_pin: pin });
      if (!res.ok) return setBulkStatus(res.error || "Proceed failed.", "error");
      setBulkStatus(`Pay finished · status ${res.data.status}.`, "ok");
      loadBulkDetail(bulkState.batchId);
      loadBulkBatchesList();
      refreshCoreState({ force: true });
    });
    view.querySelector("[data-bulk-refresh]")?.addEventListener("click", () => {
      loadBulkBatchesList();
      if (bulkState.batchId) loadBulkDetail(bulkState.batchId);
    });
    await Promise.all([
      loadBulkBatchesList(),
      loadBulkBillerCatalogue({ category: "", q: "" }),
    ]);
  }

  async function initHomeScreen() {
    await refreshCoreState();
    const outletEl = view.querySelector("[data-home-outlet]");
    if (outletEl && appState.user) {
      outletEl.textContent = appState.user.outlet_name || appState.user.account_id || appState.user.email;
    }
    const hello = view.querySelector("#hello");
    if (hello) {
      const hour = new Date().getHours();
      const part = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
      const name = (appState.user && (appState.user.display_name || appState.user.outlet_name)) || "Retailer";
      hello.textContent = `${part}, ${name}`;
    }
    const w = appState.wallet;
    if (w) {
      const avail = view.querySelector("[data-home-avail]");
      const held = view.querySelector("[data-home-held]");
      const dUsed = view.querySelector("[data-home-daily-used]");
      const dLimit = view.querySelector("[data-home-daily-limit]");
      if (avail) avail.textContent = rupee(w.available);
      if (held) held.textContent = `Held ${rupee(w.held)} · Status ${w.status}`;
      if (dUsed) dUsed.textContent = rupee(w.daily_used);
      if (dLimit) dLimit.textContent = `Limit ${rupee(w.daily_debit_limit)}`;
    }

    const ent = appState.entitlements;
    const tilesBox = view.querySelector("[data-home-tiles]");
    const railsEl = view.querySelector("[data-home-rails]");
    const cta = view.querySelector("[data-home-primary-cta]");
    const statsEl = view.querySelector(".stats");
    const recentCard = view.querySelector("[data-home-txns]")?.closest("section.card");
    const viewAll = view.querySelector("[data-home-view-all]");
    if (ent) {
      const enabled = ent.enabled_services || [];
      const modes = ent.payment_modes || {};
      if (railsEl) {
        const activeRails = [modes.wallet_pay ? "Wallet" : "", modes.pg_pay ? "PG" : ""].filter(Boolean);
        railsEl.textContent = activeRails.length ? `Payment rails: ${activeRails.join(" + ")}` : "Payment rails disabled";
      }
      if (cta) cta.hidden = !enabled.includes("bbps");
      if (statsEl) {
        const walletOn = enabled.includes("wallet");
        const txnOn = enabled.includes("transactions");
        statsEl.querySelectorAll("article.stat").forEach((stat, idx) => {
          // 0 available, 1 daily debit → wallet; 2 recent count → transactions
          if (idx < 2) stat.hidden = !walletOn;
          else stat.hidden = !txnOn;
        });
        statsEl.hidden = !walletOn && !txnOn;
      }
      if (recentCard) recentCard.hidden = !enabled.includes("transactions");
      if (viewAll) viewAll.hidden = !enabled.includes("transactions");
      if (tilesBox) {
        const defs = [
          { key: "bbps", href: "#bills", icon: "receipt_long", title: "Bill Pay (BBPS)", desc: "Fetch & settle live Bharat Connect bills." },
          { key: "bbps_bulk", href: "#bulk-bills", icon: "upload_file", title: "Bulk bills", desc: "Excel upload, fetch dues, wallet auto-pay." },
          { key: "wallet", href: "#wallet", icon: "account_balance_wallet", title: "Wallet & Float", desc: "Check balance, ledger, and submit UTR top-up." },
          { key: "transactions", href: "#transactions", icon: "history", title: "Transactions", desc: "Live BBPS history, receipts, and status sync." },
          { key: "profile", href: "#profile", icon: "person", title: "Profile & KYC", desc: "Manage outlet profile, Wallet PIN, and sessions." },
          { key: "vouchers", href: "#vouchers", icon: "confirmation_number", title: "Vouchers", desc: "Order enabled brand vouchers." },
          { key: "recharge", href: "#recharge", icon: "smartphone", title: "Recharges", desc: "Mobile and DTH recharges." },
          { key: "dmt", href: "#dmt", icon: "send", title: "DMT", desc: "Domestic money transfer." },
          { key: "aeps", href: "#aeps", icon: "fingerprint", title: "AEPS", desc: "Aadhaar cash services." },
        ];
        const allowedTiles = defs.filter((item) => {
          if (item.key === "bbps_bulk") return enabled.includes("bbps") && Boolean(ent.bbps_bulk_enabled);
          return enabled.includes(item.key);
        });
        tilesBox.innerHTML = allowedTiles.length
          ? allowedTiles
              .map(
                (item) => `<a class="tile" href="${item.href}"><span class="mi">${item.icon}</span><strong>${esc(item.title)}</strong><p>${esc(item.desc)}</p></a>`,
              )
              .join("")
          : `<p class="hint">No services are assigned to this counter. Contact admin.</p>`;
      }
    }

    const txnRes = await globalThis.PayswapHub.transactions({ service: "all" });
    const listBox = view.querySelector("[data-home-txns]");
    const countEl = view.querySelector("[data-home-txn-count]");
    const metaEl = view.querySelector("[data-home-txn-meta]");
    if (!txnRes.ok) {
      if (listBox) listBox.innerHTML = `<p class="hint">Transactions unavailable.</p>`;
      return;
    }
    const rows = Array.isArray(txnRes.data.transactions) ? txnRes.data.transactions : [];
    const okCount = rows.filter((r) => r.state === "success").length;
    const pendCount = rows.filter((r) => r.state === "pending").length;
    if (countEl) countEl.textContent = String(rows.length);
    if (metaEl) metaEl.textContent = rows.length ? `${okCount} settled · ${pendCount} pending` : "No recorded transactions yet";
    if (listBox) {
      if (!rows.length) {
        listBox.innerHTML = `<p class="hint">No live transactions recorded yet. Collect a BBPS bill to see activity here.</p>`;
      } else {
        listBox.innerHTML = rows
          .slice(0, 6)
          .map(
            (r) => `
          <div class="txn">
            <span class="txn-ico"><span class="mi">${r.direction === "CR" ? "add_card" : "receipt_long"}</span></span>
            <div class="txn-copy"><strong>${esc(r.biller || r.service)}</strong><p>${esc(r.reference)} · ${esc(r.account || "")} · ${esc((r.payment_channel || "wallet").toUpperCase())}</p></div>
            <div class="txn-side"><strong>${r.direction === "CR" ? "+" : "−"}${esc(rupee(r.amount))}</strong><span class="pill ${statePillClass(r.state)}">${esc(r.direction === "CR" ? "Credit" : `Debit · ${statusLabel(r.state)}`)}</span></div>
          </div>`,
          )
          .join("");
      }
    }
  }

  /* ── BBPS Screen ── */
  function renderBbpsConnection({ configured = false, loading = false, error = "" } = {}) {
    const box = view.querySelector("[data-bbps-connection]");
    if (!box) return;
    const title = box.querySelector("[data-bbps-connection-title]");
    const copy = box.querySelector("[data-bbps-connection-copy]");
    const refresh = box.querySelector("[data-bbps-refresh]");
    const check = box.querySelector(".bbps-check .mi");
    box.classList.toggle("is-connected", configured);
    box.classList.toggle("is-unavailable", !configured && !loading);
    box.classList.toggle("is-loading", loading);
    if (refresh) refresh.disabled = loading;
    if (check) check.textContent = loading ? "sync" : configured ? "check" : "warning";
    if (loading) {
      title.textContent = "Checking BBPS connection";
      copy.textContent = "Loading the secure biller catalogue…";
    } else if (configured) {
      title.textContent = "BBPS Connected";
      copy.textContent = "Live bill fetch, Wallet/PG settlement, and status sync are active.";
    } else if (error) {
      title.textContent = "BBPS connection unavailable";
      copy.textContent = error;
    } else {
      title.textContent = "BBPS setup required";
      copy.textContent = "Biller catalogue is loaded, but live fetch and payment wait on provider credentials.";
    }
  }

  function renderBbpsSteps(step = 1) {
    view.querySelectorAll(".bbps-steps .step").forEach((item, index) => {
      item.classList.toggle("is-current", index + 1 === step);
      item.classList.toggle("is-complete", index + 1 < step);
    });
  }

  function syncBbpsPayLabel(form) {
    const label = form?.querySelector("[data-bbps-pay-label]");
    if (!label) return;
    const amount = String(form.amount?.value || "").trim();
    label.textContent = amount ? `Pay ${rupee(amount)}` : "Pay bill";
  }

  function setBbpsPayLocked(form, locked, { title = "", copy = "" } = {}) {
    if (!form) return;
    form.classList.toggle("is-paid", locked);
    const compose = form.querySelector("[data-bbps-compose]");
    const done = form.querySelector("[data-bbps-done]");
    const payBtn = form.querySelector("[data-bbps-pay-btn]");
    const changeBtn = form.querySelector("[data-bbps-clear-op]");
    if (compose) compose.hidden = locked;
    if (done) {
      done.hidden = !locked;
      const doneTitle = done.querySelector("[data-bbps-done-title]");
      const doneCopy = done.querySelector("[data-bbps-done-copy]");
      if (doneTitle && title) doneTitle.textContent = title;
      if (doneCopy && copy) doneCopy.textContent = copy;
    }
    if (payBtn) {
      payBtn.hidden = locked;
      payBtn.disabled = locked;
    }
    if (changeBtn) changeBtn.hidden = locked;
  }

  function reopenBbpsPayCompose(form) {
    if (!form) return;
    bbpsState.lastReference = "";
    bbpsState.lastReceipt = null;
    bbpsState.lastReceiptData = null;
    sessionStorage.removeItem("payswap-bbps-attempt");
    setBbpsPayLocked(form, false);
    ["account", "amount", "customer_mobile", "remitter_name", "wallet_pin"].forEach((name) => {
      if (form[name]) form[name].value = "";
    });
    const billBox = form.querySelector("[data-bbps-bill-box]");
    const statusBox = form.querySelector("[data-bbps-status]");
    const payReceipt = form.querySelector("[data-bbps-pay-receipt]");
    const pgBox = form.querySelector("[data-bbps-pg-box]");
    const postPay = form.querySelector("[data-bbps-postpay]");
    if (billBox) {
      billBox.hidden = true;
      billBox.replaceChildren();
    }
    if (statusBox) statusBox.hidden = true;
    if (payReceipt) {
      payReceipt.hidden = true;
      payReceipt.replaceChildren();
    }
    if (pgBox) {
      pgBox.hidden = true;
      pgBox.replaceChildren();
    }
    if (postPay) postPay.hidden = true;
    syncBbpsRailControls(form);
    syncBbpsPayLabel(form);
    renderBbpsSteps(3);
    form.querySelector("[name='account']")?.focus();
  }

  function visibleBbpsAdParams(op) {
    return (op && Array.isArray(op.ad_params) ? op.ad_params : []).filter((param) => {
      if (!param || param.ui_hidden || param.hidden) return false;
      // Optional tags stay off the counter — Mobikwik accepts the bill without them.
      if (param.optional) return false;
      return true;
    });
  }

  function collectAdParams(form) {
    const out = {};
    const op = bbpsState.operator;
    // Fixed bank / Cir codes never appear as inputs; inject catalogue defaults.
    (op && Array.isArray(op.ad_params) ? op.ad_params : []).forEach((param) => {
      if (!param || !param.ui_hidden) return;
      const key = String(param.key || "").trim();
      const value = String(param.default_value || "").trim();
      if (key && value) out[key] = value;
    });
    form.querySelectorAll("[data-bbps-ad]").forEach((input) => {
      const value = String(input.value || "").trim();
      if (value) out[input.dataset.bbpsAd] = value;
    });
    return out;
  }

  function paintBbpsAdParams(adBox, op) {
    if (!adBox) return;
    adBox.replaceChildren();
    visibleBbpsAdParams(op).forEach((param) => {
      const label = document.createElement("label");
      label.className = "field";
      const title = document.createElement("span");
      title.textContent = param.label || param.key;
      label.append(title);
      const options = Array.isArray(param.options) ? param.options : [];
      if (options.length) {
        const select = document.createElement("select");
        select.dataset.bbpsAd = param.key;
        select.required = !param.optional;
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "Select";
        select.append(blank);
        options.forEach((opt) => {
          const row = document.createElement("option");
          row.value = String(opt.value || "");
          row.textContent = String(opt.label || opt.value || "");
          if (param.default_value && String(param.default_value) === row.value) row.selected = true;
          select.append(row);
        });
        label.append(select);
      } else {
        const input = document.createElement("input");
        input.dataset.bbpsAd = param.key;
        input.value = param.default_value || "";
        input.placeholder = "Required";
        input.required = !param.optional;
        input.autocomplete = "off";
        if (param.regex) input.title = `Format: ${param.regex}`;
        label.append(input);
      }
      adBox.append(label);
    });
  }

  function ensureBbpsMogo() {
    if (bbpsMogoAudio) return bbpsMogoAudio;
    bbpsMogoAudio = new Audio(absAsset(BBPS_BRAND.mogo));
    bbpsMogoAudio.preload = "auto";
    bbpsMogoAudio.setAttribute("playsinline", "true");
    return bbpsMogoAudio;
  }

  /* Browsers drop the click gesture after await — prime audio/context on Pay click before the API call. */
  function primeBbpsAudio() {
    try {
      const audio = ensureBbpsMogo();
      audio.muted = true;
      const play = audio.play();
      if (play && typeof play.then === "function") {
        play
          .then(() => {
            audio.pause();
            audio.currentTime = 0;
            audio.muted = false;
          })
          .catch(() => {
            audio.muted = false;
          });
      } else {
        audio.muted = false;
      }
    } catch {
      /* ignore */
    }
  }

  function playBbpsFailTone() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(220, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(110, ctx.currentTime + 0.28);
      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.08, ctx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.32);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.34);
      osc.onended = () => ctx.close().catch(() => {});
    } catch {
      /* ignore */
    }
  }

  function playBbpsOutcome(tone) {
    if (tone === "ok") {
      try {
        const audio = ensureBbpsMogo();
        audio.muted = false;
        audio.volume = 1;
        audio.currentTime = 0;
        const play = audio.play();
        if (play && typeof play.catch === "function") {
          play.catch(() => {
            /* gesture lost after await — still show celebration UX */
          });
        }
      } catch {
        /* ignore */
      }
      return;
    }
    if (tone === "error") playBbpsFailTone();
  }

  function dismissBbpsCelebration() {
    document.getElementById("bbps-celebrate")?.remove();
  }

  function celebrateBbpsSuccess({ amount = "", reference = "", biller = "" } = {}) {
    dismissBbpsCelebration();
    playBbpsOutcome("ok");
    const host = document.createElement("div");
    host.id = "bbps-celebrate";
    host.className = "bbps-celebrate";
    host.setAttribute("role", "dialog");
    host.setAttribute("aria-modal", "true");
    host.setAttribute("aria-label", "Payment successful");
    host.innerHTML = `
      <div class="bbps-celebrate-card">
        <div class="bbps-celebrate-burst" aria-hidden="true"></div>
        <img class="bbps-celebrate-assured" src="${esc(BBPS_BRAND.assured)}" alt="B Assured" />
        <div class="bbps-celebrate-check" aria-hidden="true"><span class="mi">check</span></div>
        <p class="bbps-celebrate-kicker">Bharat Connect</p>
        <h2>Payment successful</h2>
        <p class="bbps-celebrate-amount">${esc(amount ? rupee(amount) : "")}</p>
        <p class="bbps-celebrate-meta">${esc(biller || "Bill paid")}</p>
        <p class="bbps-celebrate-ref">Ref ${esc(reference || "—")}</p>
        <button type="button" class="btn yellow block" data-bbps-celebrate-close>Continue</button>
      </div>`;
    document.body.appendChild(host);
    requestAnimationFrame(() => host.classList.add("is-on"));
    host.querySelector("[data-bbps-celebrate-close]")?.addEventListener("click", dismissBbpsCelebration);
    host.addEventListener("click", (event) => {
      if (event.target === host) dismissBbpsCelebration();
    });
    window.setTimeout(dismissBbpsCelebration, 5200);
  }

  function showBbpsStatus(box, text, tone = "pending", { sound = false, title = "", celebrate = false, amount = "", reference = "", biller = "" } = {}) {
    if (!box) return;
    box.hidden = false;
    box.className = `bbps-status-box is-${tone}${tone === "ok" ? " is-pop" : ""}${tone === "error" ? " is-shake" : ""}`;
    const icon = tone === "ok" ? "check_circle" : tone === "error" ? "error" : "hourglass_top";
    const heading =
      title ||
      (tone === "ok" ? "Successful" : tone === "error" ? "Failed" : "In progress");
    box.innerHTML = `<span class="mi" aria-hidden="true">${icon}</span><div><strong>${esc(heading)}</strong><p>${esc(text)}</p></div>`;
    if (celebrate && tone === "ok") {
      celebrateBbpsSuccess({ amount, reference, biller });
    } else if (sound) {
      playBbpsOutcome(tone);
    }
  }

  function absAsset(path) {
    try {
      return new URL(path, location.href).href;
    } catch (_error) {
      return path;
    }
  }

  function receiptTone(state) {
    if (state === "success" || state === "ok") return "ok";
    if (state === "failed" || state === "error") return "error";
    return "pending";
  }

  function receiptTitle(tone, kind) {
    if (kind === "bill") return "Bill fetch response";
    if (tone === "ok") return "Payment successful";
    if (tone === "error") return "Payment failed";
    return "Payment pending";
  }

  function receiptStatusLabel(tone) {
    if (tone === "ok") return "SUCCESS";
    if (tone === "error") return "FAILED";
    return "PENDING";
  }

  function normalizeReceipt(payload = {}, { state, kind } = {}) {
    const tone = receiptTone(state || payload.state || "pending");
    const amount =
      payload.total_amount != null
        ? payload.total_amount
        : payload.bill_amount != null
          ? payload.bill_amount
          : payload.amount;
    return {
      kind: kind || "payment",
      tone,
      title: receiptTitle(tone, kind),
      status: receiptStatusLabel(tone),
      amountLabel: amount != null && amount !== "" ? rupee(amount) : "—",
      customer: payload.customer_name || payload.remitter_name || "—",
      biller: payload.biller || payload.biller_name || payload.service || "—",
      billerId: payload.biller_id || payload.operator_id || "",
      reference: payload.reference || "—",
      account: payload.account || payload.consumer_id || "—",
      mobile: payload.customer_mobile || "",
      paymentMode: payload.payment_mode || "",
      channel: (payload.payment_channel || "").toUpperCase(),
      billDate: payload.bill_date || "",
      billNumber: payload.bill_number || "",
      dueDate: payload.due_date || "",
      billAmount: payload.bill_amount != null ? rupee(payload.bill_amount) : payload.amount != null ? rupee(payload.amount) : "",
      ccf: payload.ccf != null ? rupee(payload.ccf) : kind === "bill" ? "" : "₹0.00",
      total: amount != null && amount !== "" ? rupee(amount) : "",
      when: payload.paid_at || payload.created_at ? formatDateTime(payload.paid_at || payload.created_at) : formatDateTime(new Date().toISOString()),
      vendorStatus: payload.vendor_status || payload.state || "",
      vendorTxn: payload.vendor_txn_id || "",
      reason: payload.error_message || "",
      verifyUrl: BBPS_BRAND.verifyUrl,
    };
  }

  function receiptRows(data) {
    const rows =
      data.kind === "bill"
        ? [
            ["Customer", data.customer],
            ["Biller", data.biller],
            ["Biller ID", data.billerId],
            ["Consumer ID", data.account],
            ["Due amount", data.billAmount || data.amountLabel],
            ["Bill number", data.billNumber],
            ["Bill date", data.billDate],
            ["Due date", data.dueDate],
          ]
        : [
            ["Customer", data.customer],
            ["Biller", data.biller],
            ["Biller ID", data.billerId],
            ["Transaction Ref ID", data.reference],
            ["Consumer ID", data.account],
            ["Customer mobile", data.mobile],
            ["Payment mode", data.paymentMode],
            ["Payment channel", data.channel],
            ["Bill date", data.billDate],
            ["Bill amount", data.billAmount],
            ["Customer convenience fee", data.ccf],
            ["Total amount", data.total || data.amountLabel],
            ["Date & time", data.when],
            ["BBPS reference number", data.vendorTxn],
            ["Verify at", data.verifyUrl],
          ];
    if (data.reason) rows.push(["Reason", data.reason]);
    return rows.filter((row) => row && row[1] != null && String(row[1]).trim() !== "");
  }

  function bbpsSlipRows(rows) {
    return rows
      .map(([label, value]) => `<div class="slip-row"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`)
      .join("");
  }

  function receiptBrandHtml(data, { absolute = false } = {}) {
    const src = (path) => esc(absolute ? absAsset(path) : path);
    const success = data.tone === "ok" && data.kind !== "bill";
    // Stage-3 success receipt: B Assured only (online → top-left). Journey/fail/fetch: Bharat Connect top-right.
    if (success) {
      return `<div class="slip-brand is-assured">
        <img class="slip-assured" src="${src(BBPS_BRAND.assured)}" alt="B Assured" />
        <img class="slip-ou" src="${src(BBPS_BRAND.ouLogo)}" alt="PaySwap" />
      </div>`;
    }
    return `<div class="slip-brand is-journey">
      <img class="slip-ou" src="${src(BBPS_BRAND.ouLogo)}" alt="PaySwap" />
      <img class="slip-bc" src="${src(BBPS_BRAND.logo)}" alt="Bharat Connect" />
    </div>`;
  }

  function receiptCardHtml(data, { download = true } = {}) {
    const rows = receiptRows(data);
    const foot =
      data.kind === "bill"
        ? "Amounts shown are from Bharat Connect. Confirm with the customer before paying."
        : `Keep this Bharat Connect reference. Verify on ${data.verifyUrl}`;
    return `<div class="slip ${data.tone === "ok" && data.kind !== "bill" ? "is-success-receipt" : ""}">
      ${receiptBrandHtml(data)}
      <div class="slip-status">
        <span class="slip-badge">${esc(data.status)}</span>
        <p class="slip-kicker">${esc(data.title)}</p>
      </div>
      <div class="slip-hero">
        <span>Total amount</span>
        <strong>${esc(data.amountLabel)}</strong>
      </div>
      <div class="slip-body">${bbpsSlipRows(rows)}</div>
      <p class="slip-foot">${esc(foot)}</p>
      ${
        download
          ? `<button type="button" class="btn yellow block slip-download" data-receipt-download>Download receipt</button>`
          : ""
      }
    </div>`;
  }

  function receiptDocumentHtml(data) {
    const rows = receiptRows(data)
      .map(
        ([label, value]) =>
          `<tr><td>${esc(label)}</td><td>${esc(value)}</td></tr>`,
      )
      .join("");
    const success = data.tone === "ok" && data.kind !== "bill";
    const toneColor = data.tone === "ok" ? "#13845e" : data.tone === "error" ? "#cf4d57" : "#b47a20";
    const toneBg = data.tone === "ok" ? "#eaf8f2" : data.tone === "error" ? "#fff0f0" : "#fff6e8";
    const foot =
      data.kind === "bill"
        ? "Amounts shown are from Bharat Connect. Confirm with the customer before paying."
        : `Keep this Bharat Connect reference. Verify on ${data.verifyUrl}`;
    // Stage-3: online Assured top-left; @media print flips Assured to top-right for paper receipt.
    const logos = success
      ? `<div class="logos is-assured">
          <img class="assured" src="${esc(absAsset(BBPS_BRAND.assured))}" alt="B Assured" />
          <img class="ou" src="${esc(absAsset(BBPS_BRAND.ouLogo))}" alt="PaySwap" />
        </div>`
      : `<div class="logos is-journey">
          <img class="ou" src="${esc(absAsset(BBPS_BRAND.ouLogo))}" alt="PaySwap" />
          <img class="bc" src="${esc(absAsset(BBPS_BRAND.logo))}" alt="Bharat Connect" />
        </div>`;
    return `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Receipt ${esc(data.reference || "")}</title>
<style>
  *{box-sizing:border-box} body{margin:0;background:#eef2f7;color:#17233b;font:14px/1.45 Helvetica,Arial,sans-serif}
  .page{min-height:100vh;display:grid;place-items:center;padding:24px}
  .card{width:min(100%,420px);background:#fff;border:1px solid #e7ecf4;border-radius:20px;overflow:hidden;box-shadow:0 18px 40px rgba(29,52,91,.1)}
  .top{padding:22px 22px 18px;background:${success ? "#fff" : "linear-gradient(160deg,#0b2744,#12355c 55%,#1b4f86)"};color:${success ? "#17233b" : "#fff"};border-bottom:${success ? "1px solid #eef2f7" : "0"}}
  .logos{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}
  .logos img{height:28px;width:auto;max-width:150px;object-fit:contain}
  .logos.is-journey .bc{height:26px}
  .logos.is-assured .assured{height:36px}
  .logos.is-assured .ou{height:22px}
  .badge{display:inline-flex;border-radius:999px;background:${toneBg};color:${toneColor};padding:5px 10px;font-size:11px;font-weight:800;letter-spacing:.08em}
  .top h1{margin:10px 0 0;font-size:22px;letter-spacing:-.03em}
  .amount{padding:20px 22px 8px;text-align:center}
  .amount span{display:block;color:#71809a;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
  .amount strong{display:block;margin-top:6px;font-size:34px;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
  table{width:100%;border-collapse:collapse;margin:8px 0 0}
  td{padding:11px 22px;border-top:1px solid #f0f3f8;vertical-align:top}
  td:first-child{width:42%;color:#71809a;font-size:12px;font-weight:650}
  td:last-child{text-align:right;font-weight:700;word-break:break-word}
  .foot{padding:16px 22px 22px;color:#71809a;font-size:12px;line-height:1.5}
  @media print{
    body{background:#fff}.page{padding:0}.card{box-shadow:none;border:0;width:100%;border-radius:0}
    .logos.is-assured{flex-direction:row-reverse}
  }
</style></head><body>
<div class="page"><article class="card">
  <header class="top">
    ${logos}
    <span class="badge">${esc(data.status)}</span>
    <h1>${esc(data.title)}</h1>
  </header>
  <div class="amount"><span>Total amount</span><strong>${esc(data.amountLabel)}</strong></div>
  <table>${rows}</table>
  <p class="foot">${esc(foot)}</p>
</article></div>
</body></html>`;
  }

  function downloadReceiptFile(data) {
    const safeRef = String(data.reference || "receipt").replace(/[^\w.-]+/g, "_").slice(0, 48);
    const filename = `PaySwap-Receipt-${safeRef}.html`;
    const blob = new Blob([receiptDocumentHtml(data)], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    return filename;
  }

  function renderBbpsComplianceReceipt(box, payload = {}, { state = "success" } = {}) {
    if (!box) return;
    const data = normalizeReceipt(payload, { state, kind: "payment" });
    box.hidden = false;
    box.className = `receipt bbps-receipt is-${data.tone}`;
    box.dataset.receiptKind = "payment";
    box.innerHTML = receiptCardHtml(data);
    bbpsState.lastReceipt = payload;
    bbpsState.lastReceiptData = data;
  }

  function renderBbpsCategories(categories) {
    const box = view.querySelector("[data-bbps-cats]");
    if (!box) return;
    bbpsState.categories = categories;
    box.replaceChildren();
    if (!categories.length) {
      const note = document.createElement("span");
      note.className = "hint";
      note.textContent = "No BBPS categories found.";
      box.append(note);
      return;
    }

    categories.forEach((cat) => {
      const btn = document.createElement("button");
      btn.type = "button";
      const isSelected = cat.id === bbpsState.category;
      btn.className = "bbps-cat-row" + (isSelected ? " is-on" : "");
      btn.dataset.bbpsCat = cat.id;

      const ico = document.createElement("span");
      ico.className = "bbps-cat-ico mi";
      ico.setAttribute("aria-hidden", "true");
      ico.textContent = BBPS_CAT_ICONS[cat.id] || "category";

      const copy = document.createElement("span");
      copy.className = "bbps-cat-copy";
      const label = document.createElement("b");
      label.textContent = cat.label;
      const cnt = document.createElement("small");
      cnt.textContent = `${Number(cat.count || 0).toLocaleString("en-IN")} billers`;
      copy.append(label, cnt);

      btn.append(ico, copy);
      box.append(btn);
    });
  }

  function renderBbpsOperators(operators, { query = "" } = {}) {
    const list = view.querySelector("[data-bbps-ops]");
    const empty = view.querySelector("[data-bbps-ops-empty]");
    const scopeNote = view.querySelector("[data-bbps-scope-note]");
    if (!list || !empty) return;
    bbpsState.operators = operators;
    const count = view.querySelector("[data-bbps-count]");
    const title = view.querySelector("[data-bbps-biller-title]");
    const activeCatObj = bbpsState.categories.find((c) => c.id === bbpsState.category);
    const totalInCat = !query && activeCatObj ? Number(activeCatObj.count || 0) : 0;
    if (count) {
      if (totalInCat > operators.length) {
        count.textContent = `Showing ${operators.length} of ${totalInCat.toLocaleString("en-IN")}`;
      } else {
        count.textContent = `${operators.length} biller${operators.length === 1 ? "" : "s"}`;
      }
    }
    if (scopeNote) {
      scopeNote.textContent = query
        ? `Filtered by “${query}”.`
        : activeCatObj
          ? "Billers for this category."
          : "Pick a service to list billers.";
    }
    const catName = view.querySelector("[data-bbps-category-name]");
    if (catName) {
      catName.textContent = query ? "Search" : activeCatObj ? activeCatObj.label : "Category";
    }
    if (title) {
      title.textContent = activeCatObj
        ? `${activeCatObj.label} Billers${totalInCat ? ` (${totalInCat.toLocaleString("en-IN")})` : ""}`
        : query
          ? "Search results"
          : "Choose Biller";
    }

    list.replaceChildren();
    if (!operators.length) {
      empty.hidden = false;
      empty.textContent = query
        ? `No billers matched “${query}”.`
        : activeCatObj
          ? "No billers found in this category."
          : "Select a category to load billers.";
      return;
    }
    empty.hidden = true;
    operators.forEach((op) => {
      const uid = op.biller_id || op.op;
      const currentUid = bbpsState.operator ? bbpsState.operator.biller_id || bbpsState.operator.op : "";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "bbps-op-row" + (currentUid === uid ? " is-on" : "");
      btn.dataset.bbpsOp = uid;
      btn.title = `${op.name} (${op.category_label || op.category})`;

      const mark = document.createElement("span");
      mark.className = "bbps-op-logo";
      const glyph = document.createElement("span");
      glyph.className = "mi";
      glyph.textContent = BBPS_CAT_ICONS[op.category] || "receipt_long";
      if (op.icon) {
        const img = document.createElement("img");
        img.src = op.icon;
        img.alt = "";
        img.loading = "lazy";
        img.referrerPolicy = "no-referrer";
        img.decoding = "async";
        img.onerror = () => {
          img.remove();
          glyph.hidden = false;
        };
        glyph.hidden = true;
        mark.append(img, glyph);
      } else {
        mark.append(glyph);
      }

      const copy = document.createElement("span");
      copy.className = "bbps-op-copy";
      const name = document.createElement("b");
      name.textContent = op.name;
      const tag = document.createElement("small");
      tag.textContent =
        op.bill_fetch === "MANDATORY" ? "Bill Fetch" : op.bill_fetch === "OPTIONAL" ? "Fetch / Direct" : "Direct Pay";
      copy.append(name, tag);

      const radio = document.createElement("span");
      radio.className = "bbps-op-radio";
      radio.setAttribute("aria-hidden", "true");
      if (currentUid === uid) {
        const check = document.createElement("span");
        check.className = "mi";
        check.textContent = "check";
        radio.append(check);
      }

      btn.append(mark, copy, radio);
      list.append(btn);
    });
  }

  function syncBbpsRailControls(form) {
    const rails = form.querySelector("[data-bbps-rails]");
    const walletHint = form.querySelector("[data-bbps-wallet-hint]");
    const pinWrap = form.querySelector("[data-bbps-pin-wrap]");
    if (!rails) return;
    const modes = (appState.entitlements && appState.entitlements.payment_modes) || { wallet_pay: true, pg_pay: true };
    const current = form.querySelector('input[name="payment_rail"]:checked')?.value || "";
    rails.replaceChildren();
    const options = [];
    if (modes.wallet_pay) {
      options.push({
        value: "wallet",
        title: "Payswap Wallet",
        copy: `Available ${rupee(appState.wallet ? appState.wallet.available : 0)}`,
        icon: "account_balance_wallet",
      });
    }
    if (modes.pg_pay) {
      options.push({
        value: "pg",
        title: "Payment Gateway",
        copy: "UPI, Cards, Net Banking & more",
        icon: "credit_card",
      });
    }
    if (!options.length) {
      const note = document.createElement("p");
      note.className = "hint";
      note.textContent = "No payment mode enabled by admin.";
      rails.append(note);
    } else {
      const preferred = options.some((o) => o.value === current) ? current : options[0].value;
      options.forEach((opt) => {
        const label = document.createElement("label");
        label.className = "bbps-rail-card" + (opt.value === preferred ? " is-on" : "");
        const input = document.createElement("input");
        input.type = "radio";
        input.name = "payment_rail";
        input.value = opt.value;
        input.dataset.bbpsRail = opt.value;
        input.checked = opt.value === preferred;
        const ico = document.createElement("span");
        ico.className = "mi";
        ico.textContent = opt.icon;
        const text = document.createElement("span");
        text.className = "bbps-rail-copy";
        const title = document.createElement("b");
        title.textContent = opt.title;
        const copy = document.createElement("small");
        copy.textContent = opt.copy;
        text.append(title, copy);
        label.append(input, ico, text);
        rails.append(label);
      });
    }
    const chosen = form.querySelector('input[name="payment_rail"]:checked')?.value || "";
    const hasPin = Boolean(appState.wallet && appState.wallet.has_pin);
    if (pinWrap) {
      pinWrap.hidden = !(chosen === "wallet" && hasPin);
      if (form.wallet_pin) form.wallet_pin.required = chosen === "wallet" && hasPin;
    }
    if (walletHint) {
      if (chosen === "wallet" && appState.wallet) {
        walletHint.textContent =
          appState.wallet.status !== "active"
            ? `Wallet is ${appState.wallet.status}.`
            : `Available ₹${appState.wallet.available} · Daily remaining ₹${(Number(appState.wallet.daily_remaining_paise || 0) / 100).toFixed(2)}`;
      } else if (chosen === "pg") {
        walletHint.textContent = appState.pgConfigured
          ? "Creates a verified PG payment order before executing BBPS."
          : "PG credentials are not configured on this server yet.";
      } else {
        walletHint.textContent = "Ask admin to enable Wallet or PG payment for your account.";
      }
    }
    rails.querySelectorAll(".bbps-rail-card").forEach((card) => {
      card.classList.toggle("is-on", Boolean(card.querySelector("input:checked")));
    });
  }

  async function loadBbpsCatalogue({ category = "", q = "" } = {}) {
    const empty = view.querySelector("[data-bbps-ops-empty]");
    const catsBox = view.querySelector("[data-bbps-cats]");
    const clearQ = view.querySelector("[data-bbps-clear-q]");
    if (clearQ) clearQ.hidden = !q;
    if (!globalThis.PayswapHub) return;
    bbpsState.loading = true;
    renderBbpsConnection({ loading: true });
    if (empty) {
      empty.hidden = false;
      empty.textContent = "Loading billers…";
    }
    let result;
    try {
      result = await globalThis.PayswapHub.bbpsOperators({ category, q, limit: 200 });
    } catch {
      bbpsState.loading = false;
      renderBbpsConnection({ error: "Could not reach the BBPS catalogue." });
      return;
    }
    bbpsState.loading = false;
    if (!result.ok) {
      bbpsState.configured = false;
      if (catsBox) catsBox.textContent = result.error || "Could not load BBPS catalogue.";
      if (empty) empty.textContent = result.error || "Could not load BBPS billers.";
      renderBbpsConnection({ error: result.error || "BBPS unavailable." });
      return;
    }
    bbpsState.configured = Boolean(result.data.configured);
    renderBbpsConnection({ configured: bbpsState.configured });
    const categories = Array.isArray(result.data.categories) ? result.data.categories : [];
    const operators = Array.isArray(result.data.operators) ? result.data.operators : [];
    if (!bbpsState.category && !q && categories.length) {
      const preferred = categories.find((c) => c.id === "ELECTRICITY") || categories[0];
      bbpsState.category = preferred.id;
      renderBbpsCategories(categories);
      renderBbpsSteps(2);
      return loadBbpsCatalogue({ category: bbpsState.category });
    }
    renderBbpsCategories(categories);
    renderBbpsOperators(operators, { query: q });
    if (!bbpsState.operator) renderBbpsSteps(bbpsState.category ? 2 : 1);
  }

  function clearBbpsOperator() {
    bbpsState.operator = null;
    bbpsState.lastReference = "";
    bbpsState.lastReceipt = null;
    bbpsState.lastReceiptData = null;
    bbpsState.plans = [];
    bbpsState.planCategory = "all";
    sessionStorage.removeItem("payswap-bbps-attempt");
    view.querySelectorAll("[data-bbps-op]").forEach((el) => {
      el.classList.remove("is-on");
      const radio = el.querySelector(".bbps-op-radio");
      if (radio) radio.replaceChildren();
    });
    const empty = view.querySelector("[data-bill-empty]");
    const form = view.querySelector("[data-bill-form]");
    if (empty) empty.hidden = false;
    if (form) {
      clearBbpsPlans(form);
      setBbpsPayLocked(form, false);
      form.hidden = true;
    }
    renderBbpsSteps(bbpsState.category ? 2 : 1);
  }

  function renderBbpsEmptyCards() {
    const walletEl = view.querySelector("[data-bbps-empty-wallet]");
    const metaEl = view.querySelector("[data-bbps-empty-wallet-meta]");
    const recentBox = view.querySelector("[data-bbps-recent]");
    const w = appState.wallet;
    if (walletEl) walletEl.textContent = rupee(w ? w.available : 0);
    if (metaEl) {
      metaEl.textContent = w
        ? `Held ${rupee(w.held)} · Status ${w.status || "—"}`
        : "Load float before peak hours";
    }
    if (!recentBox) return;
    const rows = (Array.isArray(appState.transactions) ? appState.transactions : [])
      .filter((row) => {
        const svc = String(row.service || row.payment_channel || "").toLowerCase();
        return svc.includes("bbps") || row.biller || row.biller_id;
      })
      .slice(0, 4);
    recentBox.replaceChildren();
    if (!rows.length) {
      const note = document.createElement("p");
      note.className = "hint";
      note.textContent = "Recent BBPS payments will show here.";
      recentBox.append(note);
      return;
    }
    rows.forEach((row) => {
      const item = document.createElement("div");
      item.className = "bbps-recent-row";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = row.biller || row.service || "BBPS";
      const sub = document.createElement("span");
      sub.textContent = `${row.reference || "—"} · ${row.state || "—"}`;
      copy.append(title, sub);
      const amt = document.createElement("b");
      amt.textContent = rupee(row.amount);
      item.append(copy, amt);
      recentBox.append(item);
    });
  }

  async function initBbpsScreen() {
    await refreshCoreState();
    bbpsState.operator = null;
    bbpsState.lastReference = "";
    bbpsState.configured = false;
    sessionStorage.removeItem("payswap-bbps-attempt");
    const walletChip = view.querySelector("[data-bbps-wallet-chip]");
    if (walletChip) walletChip.textContent = rupee(appState.wallet ? appState.wallet.available : 0);
    if (globalThis.PayswapHub && !(appState.transactions && appState.transactions.length)) {
      try {
        const tx = await globalThis.PayswapHub.transactions({ service: "bbps" });
        if (tx.ok && Array.isArray(tx.data?.transactions)) {
          appState.transactions = tx.data.transactions;
        }
      } catch {
        /* empty cards stay on wallet + tips */
      }
    }
    renderBbpsEmptyCards();
    renderBbpsSteps(1);
    loadBbpsCatalogue({ category: bbpsState.category });
  }

  function selectBbpsOperator(op) {
    bbpsState.operator = op;
    bbpsState.lastReference = "";
    sessionStorage.removeItem("payswap-bbps-attempt");
    const uid = op.biller_id || op.op;
    view.querySelectorAll("[data-bbps-op]").forEach((el) => {
      const on = el.dataset.bbpsOp === uid;
      el.classList.toggle("is-on", on);
      const radio = el.querySelector(".bbps-op-radio");
      if (!radio) return;
      radio.replaceChildren();
      if (on) {
        const check = document.createElement("span");
        check.className = "mi";
        check.textContent = "check";
        radio.append(check);
      }
    });
    const empty = view.querySelector("[data-bill-empty]");
    const form = view.querySelector("[data-bill-form]");
    if (empty) empty.hidden = true;
    if (!form) return;
    form.hidden = false;
    form.reset();
    setBbpsPayLocked(form, false);

    const logo = form.querySelector("[data-bill-logo]");
    const glyph = form.querySelector("[data-bill-glyph]");
    if (glyph) {
      glyph.textContent = BBPS_CAT_ICONS[op.category] || "receipt_long";
      glyph.hidden = Boolean(op.icon);
    }
    if (logo) {
      logo.hidden = !op.icon;
      logo.referrerPolicy = "no-referrer";
      logo.src = op.icon || "";
      logo.onerror = () => {
        logo.hidden = true;
        if (glyph) glyph.hidden = false;
      };
    }
    form.querySelector("[data-bill-title]").textContent = op.name;
    const fetchLabel =
      op.bill_fetch === "MANDATORY" ? "Bill fetch required" : op.bill_fetch === "OPTIONAL" ? "Bill fetch optional" : "Direct payment";
    form.querySelector("[data-bill-biller]").textContent = `${op.category_label} · ${op.biller_id || "op " + op.op} · ${fetchLabel}`;

    const prepaidLike = isPrepaidLike(op);
    const acctLabel = form.querySelector("[data-bbps-account-label]");
    if (acctLabel) acctLabel.textContent = prepaidLike ? "Mobile number" : (op.primary_param && op.primary_param.label) || "Consumer number";
    if (form.account) {
      form.account.placeholder = prepaidLike ? "10-digit mobile number" : "Enter consumer number";
      form.account.inputMode = prepaidLike ? "numeric" : "text";
    }

    const cirSelectWrap = form.querySelector("[data-bbps-cir-select-wrap]");
    const cirWrap = form.querySelector("[data-bbps-cir-wrap]");
    const cirSelect = form.querySelector("[data-bbps-circle]");
    const cirManual = form.querySelector("[data-bbps-circle-manual]");
    // Telecom circle picker only for prepaid/DTH. Fixed Cir_Id (FASTag/CC) stays hidden.
    if (cirSelectWrap) cirSelectWrap.hidden = !prepaidLike;
    if (cirWrap) cirWrap.hidden = true;
    if (cirSelect) {
      cirSelect.required = false;
      void fillBbpsCircleSelect(cirSelect, op.circle_default || "");
    }
    if (cirManual) {
      cirManual.required = false;
      cirManual.value = op.circle_default || "";
    }
    clearBbpsPlans(form);

    paintBbpsAdParams(form.querySelector("[data-bbps-ad-params]"), op);

    const fetchBtn = form.querySelector("[data-bbps-fetch]");
    if (fetchBtn) {
      fetchBtn.hidden = prepaidLike || op.bill_fetch === "NOT_REQUIRED";
      fetchBtn.disabled = !bbpsState.configured;
    }
    const plansBtn = form.querySelector("[data-bbps-load-plans]");
    if (plansBtn) {
      plansBtn.hidden = !prepaidLike;
      plansBtn.disabled = !bbpsState.configured;
    }
    const fetchNote = form.querySelector("[data-bbps-fetch-note]");
    if (fetchNote) {
      fetchNote.textContent = bbpsState.configured
        ? prepaidLike
          ? "Choose the operator and circle, then enter the mobile number. One plan request goes to Mobikwik."
          : op.bill_fetch === "NOT_REQUIRED"
            ? "This biller accepts a direct payment amount."
            : "Fetch the bill before collecting payment."
        : "Live actions unlock once BBPS provider setup is complete.";
    }
    const modeSelect = form.querySelector("select[name='payment_mode']");
    if (modeSelect) {
      modeSelect.replaceChildren();
      const modes = op.modes && op.modes.length ? op.modes : ["Cash"];
      const preferred = op.default_payment_mode || (modes.includes("Cash") ? "Cash" : modes[0]);
      modes.forEach((mode) => {
        const opt = document.createElement("option");
        opt.value = mode;
        opt.textContent = mode;
        if (mode === preferred) opt.selected = true;
        modeSelect.append(opt);
      });
    }

    if (!form.dataset.planWatch) {
      form.dataset.planWatch = "1";
      form.account?.addEventListener("input", () => scheduleBbpsPlans(form));
      form.querySelector("[data-bbps-circle]")?.addEventListener("change", () => {
        if (isPrepaidLike(bbpsState.operator)) scheduleBbpsPlans(form);
      });
    }
    syncBbpsRailControls(form);
    syncBbpsPayLabel(form);
    const billBox = form.querySelector("[data-bbps-bill-box]");
    if (billBox) billBox.hidden = true;
    const statusBox = form.querySelector("[data-bbps-status]");
    if (statusBox) statusBox.hidden = true;
    const pgBox = form.querySelector("[data-bbps-pg-box]");
    if (pgBox) pgBox.hidden = true;
    const postPay = form.querySelector("[data-bbps-postpay]");
    if (postPay) postPay.hidden = true;
    renderBbpsSteps(3);
    if (window.innerWidth < 1100) form.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function readBbpsCircle(form) {
    if (!form) return "";
    const op = bbpsState.operator;
    if (isPrepaidLike(op)) {
      return String(form.querySelector("[data-bbps-circle]")?.value || "").trim();
    }
    // FASTag / credit-card Cir_Id is a fixed catalogue code — never typed by retailer.
    if (op && op.circle_default) return String(op.circle_default).trim();
    return String(form.querySelector("[data-bbps-circle-manual]")?.value || form.circle?.value || "").trim();
  }

  async function ensureBbpsCircles() {
    if (bbpsState.circles.length) return bbpsState.circles;
    if (!globalThis.PayswapHub?.bbpsCircles) return [];
    const result = await globalThis.PayswapHub.bbpsCircles();
    if (!result.ok) {
      handleSessionRejection(result);
      return [];
    }
    bbpsState.circles = Array.isArray(result.data.circles) ? result.data.circles : [];
    return bbpsState.circles;
  }

  async function fillBbpsCircleSelect(select, preferred = "") {
    if (!select) return;
    const circles = await ensureBbpsCircles();
    const current = preferred || select.value || "";
    select.replaceChildren();
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "Select circle";
    select.append(blank);
    circles.forEach((row) => {
      const opt = document.createElement("option");
      opt.value = String(row.code || "");
      opt.textContent = `${row.label || row.code} (${row.code})`;
      if (String(row.code) === String(current)) opt.selected = true;
      select.append(opt);
    });
  }

  function clearBbpsPlans(form) {
    bbpsState.plans = [];
    bbpsState.planCategory = "all";
    const wrap = form?.querySelector("[data-bbps-plans-wrap]");
    const list = form?.querySelector("[data-bbps-plans]");
    const tabs = form?.querySelector("[data-bbps-plan-tabs]");
    const empty = form?.querySelector("[data-bbps-plans-empty]");
    const count = form?.querySelector("[data-bbps-plans-count]");
    if (wrap) wrap.hidden = true;
    if (list) list.replaceChildren();
    if (tabs) {
      tabs.hidden = true;
      tabs.replaceChildren();
    }
    if (empty) empty.hidden = true;
    if (count) count.textContent = "";
  }

  function renderBbpsPlans(form) {
    const wrap = form.querySelector("[data-bbps-plans-wrap]");
    const list = form.querySelector("[data-bbps-plans]");
    const tabs = form.querySelector("[data-bbps-plan-tabs]");
    const empty = form.querySelector("[data-bbps-plans-empty]");
    const count = form.querySelector("[data-bbps-plans-count]");
    if (!wrap || !list) return;
    wrap.hidden = false;
    const plans = bbpsState.plans || [];
    const cats = [];
    plans.forEach((plan) => {
      const cat = String(plan.category || "Other").trim() || "Other";
      if (!cats.includes(cat)) cats.push(cat);
    });
    if (tabs) {
      tabs.hidden = cats.length <= 1;
      tabs.replaceChildren();
      if (cats.length > 1) {
        ["all", ...cats].forEach((cat) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "bbps-plan-tab" + (bbpsState.planCategory === cat ? " is-on" : "");
          btn.dataset.bbpsPlanCat = cat;
          btn.textContent = cat === "all" ? "All" : cat;
          tabs.append(btn);
        });
      }
    }
    const filtered =
      bbpsState.planCategory === "all"
        ? plans
        : plans.filter((plan) => String(plan.category || "Other").trim() === bbpsState.planCategory);
    list.replaceChildren();
    filtered.forEach((plan) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "plan";
      btn.dataset.bbpsPlanAmount = String(plan.amount || "");
      btn.dataset.bbpsPlanId = String(plan.id || "");
      const amount = document.createElement("strong");
      amount.textContent = rupee(plan.amount);
      btn.append(amount);
      if (plan.validity) {
        const validity = document.createElement("small");
        validity.textContent = plan.validity;
        btn.append(validity);
      }
      if (plan.description || plan.category) {
        const desc = document.createElement("span");
        desc.textContent = plan.description || plan.category;
        btn.append(desc);
      }
      list.append(btn);
    });
    if (count) count.textContent = filtered.length ? `${filtered.length} plan${filtered.length === 1 ? "" : "s"}` : "";
    if (empty) empty.hidden = filtered.length > 0;
  }

  let bbpsPlanTimer = 0;
  let bbpsPlanFlight = "";
  let bbpsPlanKey = "";

  function bbpsPlanRequestKey(form, mobile, circle) {
    const op = bbpsState.operator ? bbpsState.operator.op || bbpsState.operator.biller_id : "";
    return `${op}|${circle}|${mobile}`;
  }

  function scheduleBbpsPlans(form) {
    window.clearTimeout(bbpsPlanTimer);
    if (!form || !isPrepaidLike(bbpsState.operator)) return;
    const mobile = String(form.account?.value || "").replace(/\D/g, "").slice(-10);
    const circle = readBbpsCircle(form);
    if (!/^[6-9]\d{9}$/.test(mobile)) {
      clearBbpsPlans(form);
      bbpsPlanKey = "";
      return;
    }
    if (!circle) return;
    const key = bbpsPlanRequestKey(form, mobile, circle);
    if (key === bbpsPlanKey && (bbpsState.plans || []).length) return;
    bbpsPlanTimer = window.setTimeout(() => loadBbpsPlans(form), 800);
  }

  async function loadBbpsPlans(form) {
    if (!globalThis.PayswapHub?.bbpsPlans || !bbpsState.operator || !form) return;
    const account = String(form.account?.value || "").trim();
    const circle = readBbpsCircle(form);
    const statusBox = form.querySelector("[data-bbps-status]");
    const mobile = account.replace(/\D/g, "").slice(-10);
    if (!/^[6-9]\d{9}$/.test(mobile)) {
      showBbpsStatus(statusBox, "Enter a valid 10-digit mobile number.", "error", { sound: true });
      return;
    }
    if (!circle) {
      showBbpsStatus(statusBox, "Select the telecom circle. Mobikwik needs the circle before plans.", "pending");
      return;
    }
    const key = bbpsPlanRequestKey(form, mobile, circle);
    if (bbpsPlanFlight) return;
    if (key === bbpsPlanKey && (bbpsState.plans || []).length) return;
    bbpsPlanFlight = key;
    const plansBtn = form.querySelector("[data-bbps-load-plans]");
    if (plansBtn) plansBtn.disabled = true;
    showBbpsStatus(statusBox, "Loading recharge plans…", "pending");
    let result;
    try {
      result = await globalThis.PayswapHub.bbpsPlans({
        biller: bbpsState.operator.biller_id || bbpsState.operator.op,
        account: mobile,
        circle,
      });
    } finally {
      bbpsPlanFlight = "";
      if (plansBtn) plansBtn.disabled = false;
    }
    if (!result || !result.ok) {
      handleSessionRejection(result);
      showBbpsStatus(statusBox, (result && result.error) || "Plans could not be loaded. Try again.", "error", {
        title: "Plans unavailable",
        sound: true,
      });
      clearBbpsPlans(form);
      return;
    }
    const resolvedCircle = String(result.data.circle || circle || "");
    if (Array.isArray(result.data.circles) && result.data.circles.length) {
      bbpsState.circles = result.data.circles;
    }
    await fillBbpsCircleSelect(form.querySelector("[data-bbps-circle]"), resolvedCircle);
    bbpsPlanKey = key;
    bbpsState.plans = Array.isArray(result.data.plans) ? result.data.plans : [];
    bbpsState.planCategory = "all";
    renderBbpsPlans(form);
    const who = [result.data.operator_name, result.data.circle_label].filter(Boolean).join(" · ");
    if (!bbpsState.plans.length) {
      showBbpsStatus(statusBox, who ? `No plans for ${who}. You can still enter an amount.` : "No plans returned. You can still enter an amount.", "pending");
    } else {
      showBbpsStatus(statusBox, `${bbpsState.plans.length} plans${who ? ` for ${who}` : ""}. Pick one or enter an amount.`, "ok");
    }
    renderBbpsSteps(4);
  }

  function showFetchedBill(box, bill, op) {
    if (!box) return;
    const billerName = (op && op.name) || (bbpsState.operator && bbpsState.operator.name) || "—";
    const billerId = (op && (op.biller_id || op.op)) || (bbpsState.operator && (bbpsState.operator.biller_id || bbpsState.operator.op)) || "—";
    const data = normalizeReceipt(
      {
        ...bill,
        biller: billerName,
        biller_id: billerId,
        amount: bill.amount,
        reference: bill.bill_number || bill.account || "bill-fetch",
      },
      { state: "pending", kind: "bill" },
    );
    if (!bill.amount) data.amountLabel = "Enter manually";
    box.hidden = false;
    box.className = "receipt bbps-receipt is-pending";
    box.dataset.receiptKind = "bill";
    box.innerHTML = receiptCardHtml(data, { download: false });
  }

  function renderWalletLedger() {
    const ledgerBox = view.querySelector("[data-w-ledger]");
    if (!ledgerBox) return;
    const allRows = Array.isArray(appState.walletLedger) ? appState.walletLedger : [];
    const dir = appState.ledgerDirFilter || "all";
    const rows = dir === "all" ? allRows : allRows.filter((e) => e.direction === dir);
    view.querySelectorAll("[data-ledger-dir]").forEach((btn) => {
      btn.classList.toggle("is-on", btn.dataset.ledgerDir === dir);
    });
    if (!rows.length) {
      ledgerBox.innerHTML = `<p class="hint">${allRows.length ? "No entries match this filter." : "No wallet ledger entries recorded yet."}</p>`;
      return;
    }
    ledgerBox.innerHTML = `<div class="table-scroll"><table class="data-table"><thead><tr><th>Type</th><th>Narration</th><th>Ref</th><th class="num">Amount</th><th class="num">Balance After</th><th>Time</th></tr></thead><tbody>${rows
      .map(
        (e) => {
          const settledHold = e.entry_type === "HOLD_CAPTURE" && e.balance_before === e.balance_after;
          const amount = settledHold ? "₹0.00" : `${e.direction === "CR" ? "+" : "-"}${rupee(e.amount)}`;
          const label = settledHold ? "SETTLED · HOLD" : `${e.direction} · ${e.entry_type}`;
          return `<tr><td><span class="pill ${e.direction === "CR" ? "ok" : "wait"}">${esc(label)}</span></td><td>${esc(e.narration)}</td><td>${esc(e.reference)}</td><td class="num">${esc(amount)}</td><td class="num">${esc(rupee(e.balance_after))}</td><td>${esc(formatDateTime(e.created_at))}</td></tr>`;
        },
      )
      .join("")}</tbody></table></div>`;
  }

  /* ── Wallet Screen ── */
  async function initWalletScreen() {
    const res = await globalThis.PayswapHub.wallet();
    if (!res.ok) {
      handleSessionRejection(res);
      return;
    }
    const {
      wallet,
      ledger,
      topup_requests: topups,
      pg_orders: pgOrders,
      entitlements,
      pg_configured: pgReady,
      pg_provider: pgProvider,
      commission,
    } = res.data;
    appState.pgConfigured = Boolean(pgReady);
    appState.pgProvider = String(pgProvider || "both").toLowerCase();
    appState.walletLedger = Array.isArray(ledger) ? ledger : [];
    updateHeaderWallet(wallet);

    const set = (sel, text) => {
      const el = view.querySelector(sel);
      if (el) el.textContent = text;
    };
    const frozenBanner = view.querySelector("[data-w-frozen-banner]");
    if (frozenBanner) {
      frozenBanner.hidden = wallet.status !== "frozen";
      set("[data-w-frozen-reason]", wallet.freeze_reason || "Contact your administrator to unfreeze wallet debits.");
    }
    set("[data-w-avail]", rupee(wallet.available));
    set("[data-w-status]", `Status: ${wallet.status}${wallet.freeze_reason ? " · " + wallet.freeze_reason : ""}`);
    set("[data-w-held]", rupee(wallet.held));
    set("[data-w-pertxn]", rupee(wallet.per_txn_limit));
    set("[data-w-minbal]", `Min balance ${rupee(wallet.min_balance)} · ${wallet.has_pin ? "PIN enabled" : "No PIN set"}`);
    set("[data-w-daily-copy]", `${rupee(wallet.daily_used)} of ${rupee(wallet.daily_debit_limit)}`);
    const comm = commission || {};
    set("[data-w-comm]", rupee(comm.commission || "0.00"));
    set(
      "[data-w-tds]",
      `TDS ${rupee(comm.tds || "0.00")} · net ${rupee(comm.net_credited || "0.00")}${
        comm.tds_section ? ` · ${comm.tds_section} ${comm.tds_rate_percent}%` : ""
      }${Number(comm.service_charge || 0) > 0 ? ` · fees ${rupee(comm.service_charge)}` : ""}`,
    );
    const bar = view.querySelector("[data-w-daily-bar]");
    if (bar) {
      const pct = wallet.daily_debit_limit_paise > 0
        ? Math.min(100, Math.round((wallet.daily_used_paise / wallet.daily_debit_limit_paise) * 100))
        : 0;
      bar.style.width = `${pct}%`;
    }

    const pgForm = view.querySelector("[data-wallet-pg-form]");
    if (pgForm) {
      pgForm.hidden = !(entitlements && entitlements.pg_topup);
      const pgHint = pgForm.querySelector("[data-w-pg-hint]");
      if (pgHint) {
        pgHint.textContent = pgReady
          ? (appState.pgProvider === "payu"
              ? "Instant wallet load via PayU Hosted Checkout."
              : appState.pgProvider === "cashfree"
                ? "Instant wallet load via Cashfree Payment Gateway."
                : "Instant wallet load via PayU or Cashfree (admin PG provider policy).")
          : "PG top-up is enabled on your account, waiting for gateway credentials on server.";
      }
    }

    const pgOrdersBox = view.querySelector("[data-w-pg-orders]");
    const pgOrdersCount = view.querySelector("[data-w-pg-orders-count]");
    if (pgOrdersCount) pgOrdersCount.textContent = pgOrders && pgOrders.length ? `${pgOrders.length} recent` : "";
    if (pgOrdersBox) {
      if (!pgOrders || !pgOrders.length) {
        pgOrdersBox.innerHTML = `<p class="hint">No PG top-up orders yet.</p>`;
      } else {
        pgOrdersBox.innerHTML = `<div class="table-scroll"><table class="data-table"><thead><tr><th>Order</th><th>Provider</th><th class="num">Amount</th><th>Status</th><th>Created</th><th>Updated</th><th></th></tr></thead><tbody>${pgOrders
          .map((p) => {
            const canPay = p.status === "created" && (p.checkout_url || p.payment_session_id);
            const actions = [
              canPay
                ? `<button type="button" class="btn xs yellow" data-cf-open-order="${esc(p.pg_order_id)}" data-cf-checkout="${esc(p.checkout_url || "")}" data-cf-session="${esc(p.payment_session_id || "")}">Pay now</button>`
                : "",
              p.status === "created"
                ? `<button type="button" class="btn xs" data-pg-verify="${esc(p.pg_order_id)}">Verify</button>`
                : "",
            ]
              .filter(Boolean)
              .join(" ");
            return `<tr>
              <td><strong class="mono">${esc(p.pg_order_id)}</strong></td>
              <td>${esc(p.provider || "—")}</td>
              <td class="num">${esc(rupee(p.amount))}</td>
              <td><span class="pill ${statePillClass(p.status)}">${esc(p.status)}</span>${p.paid_at ? `<br><small>Paid ${esc(formatDateTime(p.paid_at))}</small>` : ""}</td>
              <td>${esc(formatDateTime(p.created_at))}</td>
              <td>${esc(formatDateTime(p.updated_at))}</td>
              <td class="num">${actions || "—"}</td>
            </tr>`;
          })
          .join("")}</tbody></table></div>`;
      }
    }

    const topupCount = view.querySelector("[data-w-topups-count]");
    if (topupCount) topupCount.textContent = topups && topups.length ? `${topups.length} recent` : "";
    const topupBox = view.querySelector("[data-w-topups]");
    if (topupBox) {
      if (!topups || !topups.length) {
        topupBox.innerHTML = `<p class="hint">No UTR top-up requests submitted yet.</p>`;
      } else {
        topupBox.innerHTML = `<div class="table-scroll"><table class="data-table"><thead><tr><th>Request</th><th>Mode</th><th>UTR</th><th class="num">Amount</th><th>Status</th><th>Time</th></tr></thead><tbody>${topups
          .map(
            (r) => `<tr><td>${esc(r.request_id)}</td><td>${esc(r.mode)}</td><td>${esc(r.utr)}</td><td class="num">${esc(rupee(r.amount))}</td><td><span class="pill ${statePillClass(r.status)}">${esc(r.status)}</span></td><td>${esc(formatDateTime(r.created_at))}</td></tr>`,
          )
          .join("")}</tbody></table></div>`;
      }
    }

    renderWalletLedger();
  }

  function renderTxnFeedback() {
    const box = view.querySelector("[data-txn-feedback]");
    if (!box) return;
    const fb = appState.txnFeedback;
    if (!fb || !fb.text) {
      box.hidden = true;
      box.textContent = "";
      return;
    }
    box.hidden = false;
    box.className = `txn-feedback is-${fb.tone || "pending"}`;
    box.innerHTML = `<span>${esc(fb.text)}</span><button type="button" class="txn-feedback-close" data-txn-feedback-close aria-label="Dismiss">×</button>`;
  }

  function receiptDataFromTxn(row) {
    return normalizeReceipt(
      {
        remitter_name: row.remitter_name,
        customer_name: row.customer_name,
        biller: row.biller || row.service,
        biller_id: row.operator_id || row.biller_id,
        reference: row.reference,
        account: row.account,
        customer_mobile: row.customer_mobile,
        payment_mode: row.payment_mode,
        payment_channel: row.payment_channel || "wallet",
        amount: row.amount,
        created_at: row.created_at,
        vendor_status: row.vendor_status || row.state,
        state: row.state,
        vendor_txn_id: row.vendor_txn_id,
        error_message: row.error_message,
        service: row.service,
      },
      { state: row.state, kind: "payment" },
    );
  }

  function downloadTxnReceipt(row) {
    if (!row) return;
    const data = receiptDataFromTxn(row);
    downloadReceiptFile(data);
    appState.txnFeedback = { tone: "ok", text: `Receipt downloaded for ${row.reference}.` };
    renderTxnFeedback();
  }

  function renderTxnReceipt(row) {
    const box = view.querySelector("[data-txn-receipt]");
    if (!box) return;
    box.hidden = true;
    appState.activeReceiptRef = "";
    if (row) downloadTxnReceipt(row);
  }

  /* ── Transactions Screen ── */
  async function initTransactionsScreen() {
    const svc = appState.txnServiceFilter || "all";
    const res = await globalThis.PayswapHub.transactions({
      service: svc === "pg" ? "all" : svc,
      state: appState.txnStateFilter,
      q: appState.txnQuery,
    });
    if (!res.ok) {
      handleSessionRejection(res);
      return;
    }
    const rows = Array.isArray(res.data.transactions) ? res.data.transactions : [];
    const pgRows = Array.isArray(res.data.pg_orders) ? res.data.pg_orders : [];
    appState.transactions = rows;
    appState.pgOrders = pgRows;
    renderTxnFeedback();

    const stateBar = view.querySelector("[data-txn-state-bar]");
    if (stateBar) stateBar.hidden = svc === "pg";
    view.querySelectorAll("[data-txn-service]").forEach((btn) => {
      btn.classList.toggle("is-on", btn.dataset.txnService === svc);
    });

    const totalEl = view.querySelector("[data-txn-total]");
    const valueEl = view.querySelector("[data-txn-value]");
    const pendingEl = view.querySelector("[data-txn-pending]");
    const rowsBox = view.querySelector("[data-txn-rows]");
    const colsBox = view.querySelector("[data-txn-columns]");
    if (!rowsBox) return;

    if (svc === "pg") {
      const q = (appState.txnQuery || "").trim().toLowerCase();
      const filteredPg = q
        ? pgRows.filter((p) =>
            [p.pg_order_id, p.purpose, p.service_ref, p.provider_payment_id, p.status].some((v) =>
              String(v || "").toLowerCase().includes(q),
            ),
          )
        : pgRows;
      const paidVal = filteredPg.filter((p) => p.status === "paid").reduce((a, p) => a + Number(p.amount || 0), 0);
      const pendingPg = filteredPg.filter((p) => p.status === "created").length;
      if (totalEl) totalEl.textContent = String(filteredPg.length);
      if (valueEl) valueEl.textContent = rupee(paidVal);
      if (pendingEl) pendingEl.textContent = String(pendingPg);
      if (colsBox) colsBox.innerHTML = "<span></span><span>PG Order &amp; purpose</span><span>Service ref</span><span>Time</span><span>Amount</span><span>Status</span>";

      if (!filteredPg.length) {
        rowsBox.innerHTML = `<p class="empty-note hint">No Payment Gateway orders found for this filter.</p>`;
        return;
      }
      rowsBox.innerHTML = filteredPg
        .map(
          (p) => `
        <article class="transaction-row">
          <span class="txn-ico"><span class="mi">credit_card</span></span>
          <div class="transaction-service">
            <strong>${esc(p.pg_order_id)}</strong>
            <small>${esc(p.purpose)}${p.provider_payment_id ? " · " + esc(p.provider_payment_id) : ""}</small>
          </div>
          <div class="transaction-customer">${esc(p.service_ref || "Wallet top-up")}</div>
          <time>${esc(formatDateTime(p.created_at))}</time>
          <strong class="transaction-amount">${esc(rupee(p.amount))}</strong>
          <div class="txn-actions">
            <span class="pill ${statePillClass(p.status)}">${esc(statusLabel(p.status))}</span>
            ${p.status === "created" ? `<button type="button" class="btn xs" data-pg-verify-row="${esc(p.pg_order_id)}">Verify</button>` : ""}
          </div>
        </article>`,
        )
        .join("");
      return;
    }

    if (colsBox) {
      colsBox.innerHTML =
        "<span></span><span>Service &amp; reference</span><span>Consumer / Channel</span><span>Time</span><span>Amount</span><span>Status</span>";
    }
    const settledTotal = rows.filter((r) => r.state === "success" && r.direction !== "CR").reduce((acc, r) => acc + Number(r.amount || 0), 0);
    const pendingCount = rows.filter((r) => r.state === "pending").length;
    if (totalEl) totalEl.textContent = String(rows.length);
    if (valueEl) valueEl.textContent = rupee(settledTotal);
    if (pendingEl) pendingEl.textContent = String(pendingCount);

    if (!rows.length) {
      rowsBox.innerHTML = `<p class="empty-note hint">No live transactions found for this filter.</p>`;
      renderTxnReceipt(null);
      return;
    }
    rowsBox.innerHTML = rows
      .map((r) => {
        const isCredit = r.direction === "CR";
        const feeAmt = Number(r.fee || r.service_charge || 0);
        const feeLine = !isCredit && feeAmt > 0 ? `<small>Fee ${esc(rupee(r.fee || r.service_charge))}</small>` : "";
        const bbpsRef = !isCredit && r.vendor_txn_id ? `BBPS reference ${r.vendor_txn_id}` : "";
        const refLine = [r.reference, bbpsRef].filter(Boolean).join(" · ");
        const party = isCredit ? "Wallet credit" : `${r.account || "—"} · ${(r.payment_channel || "wallet").toUpperCase()}`;
        return `
      <article class="transaction-row">
        <span class="txn-ico${isCredit ? " is-credit" : ""}"><span class="mi">${isCredit ? "call_received" : r.service === "vouchers" ? "confirmation_number" : "receipt_long"}</span></span>
        <div class="transaction-service">
          <strong>${esc(r.biller || r.service)}</strong>
          <small>${esc(refLine)}</small>
        </div>
        <div class="transaction-customer">${esc(party)}</div>
        <time>${esc(formatDateTime(r.created_at))}</time>
        <div class="transaction-amount ${isCredit ? "is-credit" : "is-debit"}">
          <strong>${isCredit ? "+" : "−"}${esc(rupee(r.amount))}</strong>
          <small>${isCredit ? "Credit" : "Debit"}</small>
          ${feeLine}
        </div>
        <div class="txn-actions">
          <span class="pill ${statePillClass(r.state)}">${esc(statusLabel(r.state))}</span>
          ${
            r.service === "bbps" && !isCredit
              ? `<button type="button" class="btn ${r.state === "pending" ? "" : "subtle "}xs" data-txn-sync="${esc(r.reference)}">${r.state === "pending" ? "Sync status" : "Check status"}</button>`
              : ""
          }
          ${isCredit ? "" : `<button type="button" class="btn subtle xs" data-txn-receipt-ref="${esc(r.reference)}">Download</button>`}
        </div>
      </article>`;
      })
      .join("");
  }

  /* ── Profile Screen ── */
  async function initProfileScreen() {
    await refreshCoreState();
    const res = await window.PayswapSession.profile();
    if (!res.ok) return;
    const p = res.data.profile;
    const set = (sel, text) => {
      const el = view.querySelector(sel);
      if (el) el.textContent = text;
    };
    set("[data-p-id]", p.account_id || "—");
    set("[data-p-email]", p.email || "");
    set("[data-p-kyc]", p.kyc_verified ? "Verified" : "Pending checks");
    const c = p.checks || {};
    set(
      "[data-p-checks]",
      `Email:${c.email_ok ? "✓" : "–"} · Mobile(••${p.mobile_last4 || "—"}):${c.mobile_ok ? "✓" : "–"} · DigiLocker:${c.aadhaar_ok ? "✓" : "–"} · PAN(${p.pan_mask || "—"}):${c.pan_ok ? "✓" : "–"}`,
    );

    if (appState.entitlements) {
      const m = appState.entitlements.payment_modes || {};
      const modeNames = [m.wallet_pay ? "Wallet" : "", m.pg_pay ? "PG Pay" : "", m.pg_topup ? "PG Top-up" : ""].filter(Boolean);
      set("[data-p-rails]", modeNames.length ? modeNames.join(" · ") : "Restricted");
      set("[data-p-services]", "Services: " + (appState.entitlements.enabled_services || []).join(", "));
    }

    const form = view.querySelector("[data-profile-form]");
    if (form) {
      form.display_name.value = p.display_name || "";
      form.outlet_name.value = p.outlet_name || "";
      form.city.value = p.city || "";
      form.gstin.value = p.gstin || "";
      form.address.value = p.address || "";
    }

    const curPinWrap = view.querySelector("[data-pin-current-wrap]");
    const pinHint = view.querySelector("[data-pin-hint]");
    const hasPin = Boolean(appState.wallet && appState.wallet.has_pin);
    if (curPinWrap) curPinWrap.hidden = !hasPin;
    if (pinHint) {
      pinHint.textContent = hasPin
        ? "Wallet PIN is active. Enter current PIN to change it."
        : "No Wallet PIN set yet. Set a 4-6 digit PIN to protect wallet debits.";
    }

    const commRes = await globalThis.PayswapHub.commissionSummary();
    const invBox = view.querySelector("[data-p-invoices]");
    if (commRes.ok) {
      const sum = commRes.data || {};
      set("[data-p-comm]", rupee(sum.commission || "0.00"));
      set(
        "[data-p-tds]",
        `TDS ${rupee(sum.tds || "0.00")} · net ${rupee(sum.net_credited || "0.00")}${
          sum.tds_section ? ` · ${sum.tds_section} ${sum.tds_rate_percent}%` : ""
        }${Number(sum.service_charge || 0) > 0 ? ` · fees ${rupee(sum.service_charge)}` : ""}`,
      );
      set("[data-p-comm-month]", sum.month || "");
      set("[data-p-tds-rule]", sum.tds_rule || "");
      if (invBox) {
        const invoices = Array.isArray(sum.invoices) ? sum.invoices : [];
        if (!invoices.length) {
          invBox.innerHTML = sum.has_gstin
            ? `<p class="hint">No draft GST invoices yet for this account.</p>`
            : `<p class="hint">Add a GSTIN above to receive monthly tax invoices on commission. Statement figures still show MTD commission and TDS.</p>`;
        } else {
          invBox.innerHTML = `<div class="table-scroll"><table class="data-table"><thead><tr><th>Invoice</th><th>Month</th><th>Taxable</th><th>Total</th><th></th></tr></thead><tbody>${invoices
            .map(
              (inv) => `<tr>
                <td>${esc(inv.invoice_no)}</td>
                <td>${esc(inv.month)}</td>
                <td>${esc(rupee(inv.taxable))}</td>
                <td>${esc(rupee(inv.total))}</td>
                <td><button type="button" class="btn subtle xs" data-p-inv-open="${esc(inv.invoice_id)}">Open PDF</button></td>
              </tr>`,
            )
            .join("")}</tbody></table></div>`;
          const byId = Object.fromEntries(invoices.map((inv) => [inv.invoice_id, inv]));
          invBox.querySelectorAll("[data-p-inv-open]").forEach((btn) => {
            btn.addEventListener("click", () => {
              const inv = byId[btn.dataset.pInvOpen];
              if (!inv?.html) return;
              const blob = new Blob([String(inv.html)], { type: "text/html;charset=utf-8" });
              const url = URL.createObjectURL(blob);
              const w = window.open(url, "_blank", "noopener,noreferrer");
              if (!w) URL.revokeObjectURL(url);
              else window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
            });
          });
        }
      }
    } else if (invBox) {
      invBox.innerHTML = `<p class="hint">Commission summary unavailable.</p>`;
    }

    const certRes = await globalThis.PayswapHub.tdsCertificate();
    const certStatus = view.querySelector("[data-p-cert-status]");
    const certForm = view.querySelector("[data-tds-cert-form]");
    if (certRes.ok) {
      const pos = certRes.data || {};
      if (certStatus) {
        const pending = pos.pending;
        const approved = pos.approved;
        const rejected = pos.rejected;
        const rejectionNote =
          rejected && (!approved || Number(rejected.id) > Number(approved.id))
            ? ` Last request ${rejected.certificate_no} was rejected${rejected.reject_reason ? `: ${rejected.reject_reason}` : ""}.`
            : "";
        certStatus.textContent = pending
          ? `Waiting for approval: ${pending.certificate_no} at ${pending.rate_percent}% from ${pending.valid_from} to ${pending.valid_to}. Current deduction stays ${pos.tds_section} ${pos.tds_rate_percent}%.`
          : approved
            ? `Approved ${approved.certificate_no} at ${approved.rate_percent}% through ${approved.valid_to}. Refunded ₹${approved.refunded}. Credits in those dates use this rate.${rejectionNote}`
            : `${pos.rule || "No certificate on file."}${rejectionNote}`;
      }
      if (certForm) certForm.hidden = Boolean(pos.pending);
    } else if (certStatus) {
      certStatus.textContent = "Certificate status unavailable.";
    }
    if (certForm && certForm.dataset.bound !== "1") {
      certForm.dataset.bound = "1";
    certForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const result = view.querySelector("[data-p-cert-result]");
      const body = {
        certificate_no: String(certForm.certificate_no.value || "").trim().toUpperCase(),
        rate_percent: Number(certForm.rate_percent.value || 0),
        valid_from: certForm.valid_from.value,
        valid_to: certForm.valid_to.value,
      };
      const saved = await globalThis.PayswapHub.submitTdsCertificate(body);
      if (result) {
        result.hidden = false;
        result.textContent = saved.ok
          ? "Submitted. TDS stays on the current rate until an admin approves it."
          : saved.data?.error || "Could not submit the certificate.";
      }
      if (saved.ok && certStatus) {
        const pending = saved.data?.pending;
        certStatus.textContent = pending
          ? `Waiting for approval: ${pending.certificate_no} at ${pending.rate_percent}%. Current deduction is unchanged.`
          : "Submitted. TDS stays on the current rate until an admin approves it.";
        certForm.hidden = true;
      }
    });
    }

    const sessRes = await window.PayswapSession.sessions();
    const sessBox = view.querySelector("[data-p-sessions]");
    if (sessBox && sessRes.ok) {
      const list = sessRes.data.sessions || [];
      sessBox.innerHTML = list.length
        ? `<div class="table-scroll"><table class="data-table"><thead><tr><th>Device</th><th>Role</th><th>Started</th><th>Status</th></tr></thead><tbody>${list
            .map(
              (s) => `<tr><td>${esc(s.device_label || s.id.slice(0, 12) + "…")}${s.ip ? `<br><small>${esc(s.ip)}</small>` : ""}</td><td>${esc(s.role)}</td><td>${esc(new Date(s.created_at * 1000).toLocaleString("en-IN"))}</td><td><span class="pill ${s.current ? "ok" : "wait"}">${s.current ? "This browser" : "Other device"}</span></td></tr>`,
            )
            .join("")}</tbody></table></div>`
        : `<p class="hint">No active sessions.</p>`;
    }
  }

  function route() {
    let raw = (location.hash || "").replace(/^#/, "");
    try {
      raw = decodeURIComponent(raw);
    } catch (_err) {
      /* keep raw */
    }
    raw = (raw.split("?")[0].split("/")[0] || "").trim();
    if (!raw) {
      try {
        raw = sessionStorage.getItem("payswap-route") || "";
      } catch (_err) {
        raw = "";
      }
    }
    show(raw || "home");
  }

  menuBtn.addEventListener("click", () => {
    const open = !sidebar.classList.contains("is-open");
    sidebar.classList.toggle("is-open", open);
    backdrop.hidden = !open;
    menuBtn.setAttribute("aria-expanded", String(open));
  });
  backdrop.addEventListener("click", () => {
    sidebar.classList.remove("is-open");
    backdrop.hidden = true;
    menuBtn.setAttribute("aria-expanded", "false");
  });
  window.addEventListener("hashchange", route);

  view.addEventListener("click", async (event) => {
    const amt = event.target.closest("[data-amt]");
    if (amt) {
      const form = amt.closest("form");
      const input = form.querySelector("[name='amount']");
      input.value = amt.dataset.amt;
      markChips(form, amt.dataset.amt);
    }

    const bbpsCat = event.target.closest("[data-bbps-cat]");
    if (bbpsCat) {
      const next = bbpsCat.dataset.bbpsCat;
      if (next !== bbpsState.category) clearBbpsOperator();
      bbpsState.category = next;
      const qInput = view.querySelector("[data-bbps-q]");
      if (qInput) qInput.value = "";
      renderBbpsSteps(2);
      loadBbpsCatalogue({ category: bbpsState.category });
      return;
    }

    const bbpsClearQ = event.target.closest("[data-bbps-clear-q]");
    if (bbpsClearQ) {
      const qInput = view.querySelector("[data-bbps-q]");
      if (qInput) qInput.value = "";
      loadBbpsCatalogue({ category: bbpsState.category });
      return;
    }

    const bbpsClearOp = event.target.closest("[data-bbps-clear-op]");
    if (bbpsClearOp) {
      clearBbpsOperator();
      return;
    }

    const bbpsAnother = event.target.closest("[data-bbps-another]");
    if (bbpsAnother) {
      const form = view.querySelector("[data-bill-form]");
      reopenBbpsPayCompose(form);
      return;
    }

    const bbpsRefresh = event.target.closest("[data-bbps-refresh]");
    if (bbpsRefresh) {
      const query = String(view.querySelector("[data-bbps-q]")?.value || "").trim();
      loadBbpsCatalogue({ category: query ? "" : bbpsState.category, q: query });
      return;
    }

    const bbpsOp = event.target.closest("[data-bbps-op]");
    if (bbpsOp) {
      const uid = bbpsOp.dataset.bbpsOp;
      const op = bbpsState.operators.find((item) => (item.biller_id || item.op) === uid);
      if (op) selectBbpsOperator(op);
      return;
    }

    const planTab = event.target.closest("[data-bbps-plan-cat]");
    if (planTab) {
      bbpsState.planCategory = planTab.dataset.bbpsPlanCat || "all";
      const form = view.querySelector("[data-bill-form]");
      if (form) renderBbpsPlans(form);
      return;
    }

    const planPick = event.target.closest("[data-bbps-plan-amount]");
    if (planPick) {
      const form = view.querySelector("[data-bill-form]");
      if (!form) return;
      const amount = String(planPick.dataset.bbpsPlanAmount || "").trim();
      if (form.amount) form.amount.value = amount;
      form.querySelectorAll("[data-bbps-plans] .plan").forEach((btn) => {
        btn.classList.toggle("is-on", btn === planPick);
      });
      syncBbpsPayLabel(form);
      renderBbpsSteps(4);
      return;
    }

    const bbpsLoadPlans = event.target.closest("[data-bbps-load-plans]");
    if (bbpsLoadPlans && bbpsState.operator) {
      await loadBbpsPlans(view.querySelector("[data-bill-form]"));
      return;
    }

    const bbpsFetch = event.target.closest("[data-bbps-fetch]");
    if (bbpsFetch && bbpsState.operator) {
      const form = view.querySelector("[data-bill-form]");
      const statusBox = form.querySelector("[data-bbps-status]");
      const billBox = form.querySelector("[data-bbps-bill-box]");
      const account = String(form.account.value || "").trim();
      if (!account) return setError(form.account, "Enter consumer number first.");
      bbpsFetch.disabled = true;
      statusBox.hidden = true;
      billBox.hidden = true;
      const result = await globalThis.PayswapHub.fetchBbpsBill(
        {
          biller: bbpsState.operator.biller_id || bbpsState.operator.op,
          account,
          circle: readBbpsCircle(form),
          payment_mode: String(form.payment_mode?.value || ""),
          ad_params: collectAdParams(form),
        },
        crypto.randomUUID(),
      );
      bbpsFetch.disabled = false;
      if (!result.ok) {
        handleSessionRejection(result);
        showBbpsStatus(statusBox, result.error || "This bill could not be fetched. Check the account and try again.", "error", {
          title: "Bill fetch failed",
          sound: true,
        });
        return;
      }
      const bill = result.data.bill || {};
      showFetchedBill(billBox, bill, bbpsState.operator);
      if (bill.amount) form.amount.value = bill.amount;
      showBbpsStatus(statusBox, "Bill fetched from Bharat Connect. Confirm amount with the customer.", "ok", {
        title: "Bill fetched",
      });
      syncBbpsPayLabel(form);
      renderBbpsSteps(4);
      return;
    }

    const bbpsCheck = event.target.closest("[data-bbps-check-status]");
    if (bbpsCheck && bbpsState.lastReference) {
      const form = view.querySelector("[data-bill-form]");
      const statusBox = form.querySelector("[data-bbps-status]");
      bbpsCheck.disabled = true;
      primeBbpsAudio();
      const result = await globalThis.PayswapHub.bbpsStatus(bbpsState.lastReference);
      bbpsCheck.disabled = false;
      if (!result.ok) handleSessionRejection(result);
      if (result.ok) {
        const tone = result.data.state === "success" ? "ok" : result.data.state === "failed" ? "error" : "pending";
        showBbpsStatus(
          statusBox,
          `Reference ${result.data.reference} · ${result.data.vendor_status} (${result.data.state})`,
          tone,
          {
            sound: tone === "error",
            celebrate: tone === "ok",
            amount: result.data.amount || form.amount?.value,
            reference: result.data.reference,
            biller: bbpsState.operator?.name || "",
            title: tone === "ok" ? "Payment successful" : "",
          },
        );
        const payReceipt = form.querySelector("[data-bbps-pay-receipt]");
        if (payReceipt) {
          renderBbpsComplianceReceipt(payReceipt, {
            ...result.data,
            biller: bbpsState.operator?.name || result.data.biller,
            biller_id: bbpsState.operator?.biller_id || bbpsState.operator?.op,
            account: form.account?.value,
            customer_mobile: form.customer_mobile?.value,
            remitter_name: form.remitter_name?.value,
            payment_mode: form.payment_mode?.value,
          }, { state: result.data.state });
        }
        const printBtn = form.querySelector("[data-bbps-print-receipt]");
        if (printBtn) printBtn.hidden = false;
      } else {
        showBbpsStatus(statusBox, result.error || "Status could not be checked. Try again.", "error", {
          title: "Status check failed",
          sound: true,
        });
      }
      if (result.ok && result.data.wallet) updateHeaderWallet(result.data.wallet);
      return;
    }

    const bbpsLookup = event.target.closest("[data-bbps-lookup-status]");
    if (bbpsLookup) {
      const refInput = view.querySelector("[data-bbps-status-ref]");
      const outBox = view.querySelector("[data-bbps-lookup-result]");
      const reference = String(refInput?.value || "").trim();
      if (!reference) {
        if (refInput) setError(refInput, "Enter payment reference first.");
        return;
      }
      bbpsLookup.disabled = true;
      outBox.hidden = false;
      outBox.className = "bbps-lookup-box txn-lookup-box is-pending";
      outBox.textContent = "Checking reference status…";
      const result = await globalThis.PayswapHub.bbpsStatus(reference);
      bbpsLookup.disabled = false;
      if (!result.ok) handleSessionRejection(result);
      if (result.ok) {
        const tone = result.data.state === "success" ? "ok" : result.data.state === "failed" ? "error" : "pending";
        outBox.className = `bbps-lookup-box txn-lookup-box is-${tone}`;
        outBox.innerHTML = `<strong>${tone === "ok" ? "Successful" : tone === "error" ? "Failed" : "Pending"}</strong><br>Transaction ${esc(result.data.reference)} · ${esc(statusLabel(result.data.state))}${result.data.vendor_txn_id ? " · BBPS reference " + esc(result.data.vendor_txn_id) : ""}`;
        if (tone === "ok" || tone === "error") playBbpsOutcome(tone);
      } else {
        outBox.className = "bbps-lookup-box txn-lookup-box is-error";
        outBox.textContent = result.error || "Status could not be checked. Try again.";
        playBbpsOutcome("error");
      }
      if (result.ok && result.data.wallet) updateHeaderWallet(result.data.wallet);
      return;
    }

    const cfRetry = event.target.closest("[data-cf-retry-session]");
    if (cfRetry) {
      openCashfreeCheckout({
        payment_session_id: cfRetry.dataset.cfRetrySession,
        cashfree_mode: cfRetry.dataset.cfMode || "sandbox",
      });
      return;
    }

    const cfOpenOrder = event.target.closest("[data-cf-open-order]");
    if (cfOpenOrder) {
      openCashfreeCheckout({
        checkout_url: cfOpenOrder.dataset.cfCheckout || "",
        payment_session_id: cfOpenOrder.dataset.cfSession || "",
      });
      return;
    }

    const pgVerifyBtn = event.target.closest("[data-pg-verify]");
    if (pgVerifyBtn) {
      pgVerifyBtn.disabled = true;
      const orderId = pgVerifyBtn.dataset.pgVerify;
      primeBbpsAudio();
      const res = await globalThis.PayswapHub.verifyPgOrder(orderId, crypto.randomUUID());
      pgVerifyBtn.disabled = false;
      const box = pgVerifyBtn.closest(".receipt") || pgVerifyBtn.closest("[data-w-pg-box]") || pgVerifyBtn.parentElement;
      if (res.ok) {
        if (res.data.wallet) updateHeaderWallet(res.data.wallet);
        if (
          res.data.status !== "paid" &&
          res.data.provider === "cashfree" &&
          (res.data.checkout_url || res.data.payment_session_id)
        ) {
          if (box) {
            const msg = document.createElement("p");
            msg.className = "hint";
            msg.textContent = `Order ${orderId} still unpaid (${res.data.gateway_status || res.data.status}). Opening Cashfree…`;
            box.append(msg);
          }
          openCashfreeCheckout(res.data);
          return;
        }
        if (box) {
          const msg = document.createElement("p");
          msg.className = "hint";
          msg.textContent = `Order ${orderId} · status: ${res.data.status}${res.data.reference ? " · BBPS ref " + res.data.reference + " (" + res.data.state + ")" : ""}`;
          box.append(msg);
        }
        if (res.data.state === "success") {
          celebrateBbpsSuccess({
            amount: res.data.amount || "",
            reference: res.data.reference || orderId,
            biller: bbpsState.operator?.name || "",
          });
        } else if (res.data.status === "paid") {
          showPgOutcome({
            ok: true,
            amount: res.data.amount || "",
            orderId,
            detail: "Top-up settled on your wallet.",
          });
        } else if (res.data.status === "failed" || res.data.state === "failed") {
          showPgOutcome({
            ok: false,
            orderId,
            detail: "Gateway reported a failed or cancelled payment.",
          });
        }
        if (location.hash === "#wallet") initWalletScreen();
      } else {
        if (box) {
          const msg = document.createElement("p");
          msg.className = "error";
          msg.textContent = res.error || "Verification failed.";
          box.append(msg);
        }
      }
      return;
    }

    const walletRefresh = event.target.closest("[data-wallet-refresh]");
    if (walletRefresh) {
      walletRefresh.disabled = true;
      await initWalletScreen();
      walletRefresh.disabled = false;
      return;
    }

    const ledgerDirBtn = event.target.closest("[data-ledger-dir]");
    if (ledgerDirBtn) {
      appState.ledgerDirFilter = ledgerDirBtn.dataset.ledgerDir || "all";
      renderWalletLedger();
      return;
    }

    const txnSvcBtn = event.target.closest("[data-txn-service]");
    if (txnSvcBtn) {
      appState.txnServiceFilter = txnSvcBtn.dataset.txnService || "all";
      initTransactionsScreen();
      return;
    }

    const pgVerifyRow = event.target.closest("[data-pg-verify-row]");
    if (pgVerifyRow) {
      pgVerifyRow.disabled = true;
      const res = await globalThis.PayswapHub.verifyPgOrder(pgVerifyRow.dataset.pgVerifyRow, crypto.randomUUID());
      pgVerifyRow.disabled = false;
      if (
        res.ok &&
        res.data.status !== "paid" &&
        res.data.provider === "cashfree" &&
        res.data.payment_session_id
      ) {
        openCashfreeCheckout(res.data);
      }
      if (res.ok && res.data.wallet) updateHeaderWallet(res.data.wallet);
      await initTransactionsScreen();
      return;
    }

    const txnStateBtn = event.target.closest("[data-txn-state]");
    if (txnStateBtn) {
      txnStateBtn.parentElement.querySelectorAll("[data-txn-state]").forEach((b) => b.classList.toggle("is-on", b === txnStateBtn));
      appState.txnStateFilter = txnStateBtn.dataset.txnState || "all";
      initTransactionsScreen();
      return;
    }

    const txnRefresh = event.target.closest("[data-txn-refresh]");
    if (txnRefresh) {
      initTransactionsScreen();
      return;
    }

    const syncBtn = event.target.closest("[data-txn-sync]");
    if (syncBtn) {
      const ref = syncBtn.dataset.txnSync || "";
      const prevLabel = syncBtn.textContent;
      syncBtn.disabled = true;
      syncBtn.textContent = "Checking…";
      const res = await globalThis.PayswapHub.bbpsStatus(ref);
      syncBtn.disabled = false;
      syncBtn.textContent = prevLabel;
      if (!res.ok) handleSessionRejection(res);
      if (res.ok) {
        if (res.data.wallet) updateHeaderWallet(res.data.wallet);
        const tone = res.data.state === "success" ? "ok" : res.data.state === "failed" ? "error" : "pending";
        appState.txnFeedback = {
          tone,
          text: `Transaction ${res.data.reference} · ${statusLabel(res.data.state)}${res.data.vendor_txn_id ? " · BBPS reference " + res.data.vendor_txn_id : ""}`,
        };
      } else {
        appState.txnFeedback = {
          tone: "error",
          text: `Status check failed for ${ref}: ${res.error || "Unknown error"}`,
        };
      }
      await initTransactionsScreen();
      return;
    }

    const fbClose = event.target.closest("[data-txn-feedback-close]");
    if (fbClose) {
      appState.txnFeedback = null;
      renderTxnFeedback();
      return;
    }

    const rcptBtn = event.target.closest("[data-txn-receipt-ref]");
    if (rcptBtn) {
      const ref = rcptBtn.dataset.txnReceiptRef;
      const row = appState.transactions.find((t) => t.reference === ref);
      if (row) downloadTxnReceipt(row);
      return;
    }

    const downloadBtn = event.target.closest("[data-receipt-download], [data-bbps-print-receipt]");
    if (downloadBtn) {
      const data =
        bbpsState.lastReceiptData ||
        normalizeReceipt(bbpsState.lastReceipt || {}, {
          state: (bbpsState.lastReceipt && bbpsState.lastReceipt.state) || "success",
          kind: "payment",
        });
      downloadReceiptFile(data);
      const label = downloadBtn.textContent;
      downloadBtn.textContent = "Downloaded";
      window.setTimeout(() => {
        downloadBtn.textContent = label || "Download receipt";
      }, 1400);
      return;
    }

    const revokeBtn = event.target.closest("[data-revoke-sessions]");
    if (revokeBtn) {
      revokeBtn.disabled = true;
      await window.PayswapSession.revokeOtherSessions();
      revokeBtn.disabled = false;
      initProfileScreen();
    }
  });

  view.addEventListener("change", (event) => {
    if (event.target.matches("[data-bbps-rail], input[name='payment_rail']")) {
      const form = event.target.closest("form");
      if (form) syncBbpsRailControls(form);
    }
  });

  view.addEventListener("input", (event) => {
    const field = event.target;
    if (field.matches("input, textarea, select")) clearError(field);
    if (field.matches("[data-bbps-q]")) {
      const query = field.value.trim();
      clearTimeout(bbpsState.searchTimer);
      bbpsState.searchTimer = setTimeout(() => {
        loadBbpsCatalogue({ category: bbpsState.category, q: query });
      }, 180);
    }
    if (field.matches("[data-txn-q]")) {
      appState.txnQuery = field.value.trim();
      clearTimeout(txnSearchTimer);
      txnSearchTimer = setTimeout(() => initTransactionsScreen(), 220);
    }
    if (field.closest("[data-bill-form]")) {
      sessionStorage.removeItem("payswap-bbps-attempt");
    }
    if (field.name === "amount") {
      const form = field.closest("form");
      if (form) {
        markChips(form, field.value.trim());
        syncBbpsPayLabel(form);
      }
    }
    if (field.name === "customer_mobile" || field.name === "customer_phone") {
      field.value = field.value.replace(/\D/g, "").slice(0, 10);
    }
  });

  view.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    event.preventDefault();
    const data = new FormData(form);

    if (form.matches("[data-bill-form]")) {
      const statusBox = form.querySelector("[data-bbps-status]");
      const pgBox = form.querySelector("[data-bbps-pg-box]");
      const payReceipt = form.querySelector("[data-bbps-pay-receipt]");
      const postPay = form.querySelector("[data-bbps-postpay]");
      const printBtn = form.querySelector("[data-bbps-print-receipt]");
      if (form.classList.contains("is-paid")) {
        showBbpsStatus(statusBox, "This payment is already submitted. Use Pay another bill for a new collection.", "pending");
        return;
      }
      if (pgBox) pgBox.hidden = true;
      if (payReceipt) payReceipt.hidden = true;
      if (printBtn) printBtn.hidden = true;
      if (!globalThis.PayswapHub || !bbpsState.operator) {
        showBbpsStatus(statusBox, "Choose a BBPS biller first.", "error", { sound: true });
        return;
      }
      const rail = String(data.get("payment_rail") || "");
      if (!rail) {
        showBbpsStatus(statusBox, "No payment mode enabled on this retailer account.", "error", { sound: true });
        return;
      }
      const account = String(data.get("account") || "").trim();
      const amount = String(data.get("amount") || "").trim();
      const circle = readBbpsCircle(form);
      if (!account) return setError(form.account, "Enter consumer number.");
      if (!Number(amount) || Number(amount) <= 0) return setError(form.amount, "Enter a valid amount.");
      if (isPrepaidLike(bbpsState.operator) && !circle) {
        showBbpsStatus(statusBox, "Select a telecom circle before paying.", "error", { sound: true });
        return;
      }
      let mobile = String(data.get("customer_mobile") || "").trim();
      if (!mobile && isPrepaidLike(bbpsState.operator)) {
        mobile = account.replace(/\D/g, "").slice(-10);
      }
      if (mobile && !/^\d{10}$/.test(mobile)) return setError(form.customer_mobile, "Enter a 10-digit mobile.");
      const remitter = String(data.get("remitter_name") || "").trim();
      const paymentMode = String(data.get("payment_mode") || "Cash").trim();

      const keyName = "payswap-bbps-attempt";
      const submitBtn = form.querySelector("[type='submit']");
      submitBtn.disabled = true;
      if (postPay) postPay.hidden = true;
      primeBbpsAudio();
      showBbpsStatus(statusBox, "Submitting payment to Bharat Connect…", "pending");
      let result;
      try {
        result = await globalThis.PayswapHub.payBbpsBill(
          {
            biller: bbpsState.operator.biller_id || bbpsState.operator.op,
            account,
            amount,
            circle,
            customer_mobile: mobile,
            remitter_name: remitter,
            payment_mode: paymentMode,
            payment_rail: rail,
            wallet_pin: String(data.get("wallet_pin") || "").trim(),
            ad_params: collectAdParams(form),
          },
          attemptKey(keyName),
        );
      } catch {
        showBbpsStatus(statusBox, "Bill payment failed because the hub API is unavailable.", "error", { sound: true });
        submitBtn.disabled = false;
        return;
      }
      if (result.ok || result.code === "idempotency_conflict") sessionStorage.removeItem(keyName);
      if (result.ok) {
        if (result.data.wallet) updateHeaderWallet(result.data.wallet);
        if (result.data.payment_channel === "pg") {
          if (result.data.provider === "payu" && result.data.action && result.data.params) {
            showBbpsStatus(statusBox, `Redirecting to PayU for ${rupee(result.data.amount)}…`, "pending");
            if (!submitPayuHostedCheckout(result.data)) {
              showBbpsStatus(statusBox, "Could not open PayU checkout.", "error", { sound: true });
              submitBtn.disabled = false;
            }
            return;
          }
          if (result.data.provider === "cashfree" && (result.data.checkout_url || result.data.payment_session_id)) {
            showBbpsStatus(statusBox, `Redirecting to Cashfree for ${rupee(result.data.amount)}…`, "pending");
            if (!openCashfreeCheckout(result.data)) {
              showBbpsStatus(statusBox, "Could not open Cashfree checkout. Hard-refresh and retry.", "error", { sound: true });
              submitBtn.disabled = false;
            }
            return;
          }
          showBbpsStatus(statusBox, `PG order ${result.data.pg_order_id} created for ${rupee(result.data.amount)}. Complete payment on gateway then verify below.`, "pending");
          setBbpsPayLocked(form, true, {
            title: "Checkout started",
            copy: "Finish payment on the gateway, then verify below. Do not submit this bill again.",
          });
          if (postPay) postPay.hidden = false;
          if (printBtn) printBtn.hidden = true;
          if (pgBox) {
            const pgData = normalizeReceipt(
              {
                reference: result.data.reference || result.data.pg_order_id,
                biller: bbpsState.operator.name,
                biller_id: bbpsState.operator.biller_id || bbpsState.operator.op,
                account,
                amount: result.data.amount,
                payment_channel: "pg",
                payment_mode: "PG",
                vendor_status: "checkout",
                vendor_txn_id: result.data.pg_order_id,
              },
              { state: "pending", kind: "payment" },
            );
            pgData.title = "Payment Gateway checkout";
            pgData.status = "CHECKOUT";
            pgBox.hidden = false;
            pgBox.className = "receipt bbps-receipt is-pending";
            pgBox.dataset.receiptKind = "payment";
            renderPgCheckoutReceipt(pgBox, receiptCardHtml(pgData, { download: false }), {
              checkoutUrl: result.data.checkout_url,
              verifyId: result.data.pg_order_id,
            });
            bbpsState.lastReceiptData = pgData;
          }
          renderBbpsSteps(4);
        } else {
          bbpsState.lastReference = result.data.reference || "";
          const refInput = view.querySelector("[data-bbps-status-ref]");
          if (refInput && bbpsState.lastReference) refInput.value = bbpsState.lastReference;
          const tone = result.data.state === "success" ? "ok" : result.data.state === "failed" ? "error" : "pending";
          showBbpsStatus(
            statusBox,
            tone === "ok"
              ? `Paid ${rupee(result.data.amount)} · Ref ${result.data.reference}`
              : tone === "error"
                ? `Payment failed · Ref ${result.data.reference} · ${result.data.vendor_status || result.data.state}`
                : `Submitted · Ref ${result.data.reference} · ${result.data.vendor_status || result.data.state}`,
            tone,
            {
              sound: tone === "error",
              celebrate: tone === "ok",
              amount: result.data.amount,
              reference: result.data.reference,
              biller: bbpsState.operator.name,
              title: tone === "ok" ? "Payment successful" : tone === "error" ? "Payment failed" : "Payment pending",
            },
          );
          renderBbpsComplianceReceipt(payReceipt, {
            customer_name: remitter,
            remitter_name: remitter,
            biller: bbpsState.operator.name,
            biller_id: bbpsState.operator.biller_id || bbpsState.operator.op,
            reference: result.data.reference,
            account,
            customer_mobile: mobile,
            payment_mode: paymentMode,
            payment_channel: result.data.payment_channel || "wallet",
            amount: result.data.amount,
            total_amount: result.data.amount,
            ccf: 0,
            vendor_status: result.data.vendor_status,
            vendor_txn_id: result.data.vendor_txn_id,
            state: result.data.state,
            created_at: result.data.created_at || new Date().toISOString(),
            error_message: result.data.error_message,
          }, { state: result.data.state });
          if (tone === "error") {
            bbpsState.lastReference = "";
            setBbpsPayLocked(form, false);
            if (postPay) postPay.hidden = true;
            if (printBtn) printBtn.hidden = false;
            submitBtn.disabled = false;
          } else {
            setBbpsPayLocked(form, true, {
              title: tone === "ok" ? "Payment successful" : "Payment submitted",
              copy:
                tone === "ok"
                  ? "This bill is paid. Download the receipt or start a new collection for the next customer."
                  : "This payment is already submitted and waiting on Bharat Connect. Do not pay again — check live status or start a new bill.",
            });
            if (postPay) postPay.hidden = !bbpsState.lastReference;
            if (printBtn) printBtn.hidden = false;
            renderBbpsSteps(4);
          }
        }
      } else {
        handleSessionRejection(result);
        showBbpsStatus(statusBox, result.error || "The payment could not be completed. Try again.", "error", {
          title: "Payment failed",
          sound: true,
        });
        setBbpsPayLocked(form, false);
        if (payReceipt) {
          renderBbpsComplianceReceipt(payReceipt, {
            customer_name: remitter,
            biller: bbpsState.operator.name,
            biller_id: bbpsState.operator.biller_id || bbpsState.operator.op,
            account,
            customer_mobile: mobile,
            payment_mode: paymentMode,
            payment_channel: rail,
            amount,
            error_message: result.error,
            state: "failed",
          }, { state: "failed" });
          if (printBtn) printBtn.hidden = false;
        }
        submitBtn.disabled = false;
      }
      return;
    }

    if (form.matches("[data-wallet-utr-form]")) {
      const statusEl = form.querySelector("[data-w-utr-status]");
      const btn = form.querySelector("[type='submit']");
      btn.disabled = true;
      statusEl.hidden = false;
      const res = await globalThis.PayswapHub.submitTopup(
        {
          amount: String(data.get("amount") || "").trim(),
          mode: String(data.get("mode") || "BANK_TRANSFER"),
          utr: String(data.get("utr") || "").trim(),
          remarks: String(data.get("remarks") || "").trim(),
        },
        crypto.randomUUID(),
      );
      btn.disabled = false;
      if (res.ok) {
        statusEl.textContent = `Request ${res.data.request_id} submitted for Admin approval.`;
        form.utr.value = "";
        initWalletScreen();
      } else {
        statusEl.textContent = res.error || "Could not submit top-up request.";
      }
      return;
    }

    if (form.matches("[data-wallet-pg-form]")) {
      const statusEl = form.querySelector("[data-w-pg-status]");
      const pgBox = form.querySelector("[data-w-pg-box]");
      const btn = form.querySelector("[type='submit']");
      btn.disabled = true;
      statusEl.hidden = false;
      const res = await globalThis.PayswapHub.createPgOrder(
        {
          amount: String(data.get("amount") || "").trim(),
          customer_phone: String(data.get("customer_phone") || "").trim(),
        },
        crypto.randomUUID(),
      );
      btn.disabled = false;
      if (res.ok) {
        if (res.data.provider === "payu" && res.data.action && res.data.params) {
          statusEl.textContent = `Redirecting to PayU for order ${res.data.pg_order_id}…`;
          if (!submitPayuHostedCheckout(res.data)) {
            statusEl.textContent = "Could not open PayU checkout.";
          }
          return;
        }
        if (res.data.provider === "cashfree" && (res.data.checkout_url || res.data.payment_session_id)) {
          statusEl.textContent = `Redirecting to Cashfree for order ${res.data.pg_order_id}…`;
          if (!openCashfreeCheckout(res.data)) {
            statusEl.textContent = "Could not open Cashfree. Use Pay now below.";
            if (pgBox) {
              pgBox.hidden = false;
              renderPgWalletBox(pgBox, {
                orderId: res.data.pg_order_id,
                amount: rupee(res.data.amount),
                checkoutUrl: res.data.checkout_url,
                linkLabel: "Open Cashfree",
                verifyId: res.data.pg_order_id,
              });
            }
          }
          return;
        }
        statusEl.textContent = `PG order ${res.data.pg_order_id} created.`;
        if (pgBox) {
          pgBox.hidden = false;
          renderPgWalletBox(pgBox, {
            orderId: res.data.pg_order_id,
            amount: rupee(res.data.amount),
            checkoutUrl: res.data.checkout_url,
            linkLabel: "Pay Now",
            verifyId: res.data.pg_order_id,
          });
        }
      } else {
        statusEl.textContent = res.error || "Could not start PG order.";
      }
      return;
    }

    if (form.matches("[data-profile-form]")) {
      const statusEl = form.querySelector("[data-p-save-status]");
      statusEl.hidden = false;
      const res = await window.PayswapSession.updateProfile({
        display_name: String(data.get("display_name") || "").trim(),
        outlet_name: String(data.get("outlet_name") || "").trim(),
        city: String(data.get("city") || "").trim(),
        gstin: String(data.get("gstin") || "").trim(),
        address: String(data.get("address") || "").trim(),
      });
      statusEl.textContent = res.ok ? "Profile updated." : res.data.error || "Could not update profile.";
      return;
    }

    if (form.matches("[data-pin-form]")) {
      const statusEl = form.querySelector("[data-pin-status]");
      statusEl.hidden = false;
      const res = await globalThis.PayswapHub.setWalletPin({
        current_pin: String(data.get("current_pin") || "").trim(),
        new_pin: String(data.get("new_pin") || "").trim(),
      });
      if (res.ok) {
        if (res.data.wallet) updateHeaderWallet(res.data.wallet);
        statusEl.textContent = "Wallet PIN saved.";
        form.reset();
        initProfileScreen();
      } else {
        statusEl.textContent = res.error || "Could not save PIN.";
      }
      return;
    }

    if (form.matches("[data-password-form]")) {
      const statusEl = form.querySelector("[data-pw-status]");
      statusEl.hidden = false;
      const res = await window.PayswapSession.changePassword({
        current_password: String(data.get("current_password") || ""),
        new_password: String(data.get("new_password") || ""),
      });
      statusEl.textContent = res.ok
        ? "Password updated and other sessions signed out."
        : res.data.error || "Could not change password.";
      if (res.ok) form.reset();
      return;
    }

    if (form.matches("[data-voucher-form]")) {
      const status = form.querySelector("[data-voucher-status]");
      status.hidden = false;
      const keyName = "payswap-voucher-attempt";
      const button = form.querySelector("[type='submit']");
      button.disabled = true;
      const result = await globalThis.PayswapHub.orderVoucher(
        {
          brand: String(data.get("brand") || "").trim(),
          amount: String(data.get("amount") || "").trim(),
        },
        attemptKey(keyName),
      );
      if (result.ok || result.code === "idempotency_conflict") sessionStorage.removeItem(keyName);
      status.textContent = result.ok
        ? `Order ${result.data.reference} recorded.`
        : result.error || "The order could not be placed. Try again.";
      button.disabled = false;
    }
  });

  const session = window.PayswapSession;
  const gate = document.getElementById("gate");
  const shell = document.querySelector(".shell");

  async function handleSessionRejection(result) {
    if (!result || (result.status !== 401 && result.status !== 403)) return;
    if (result.code === "service_disabled" || result.code === "payment_mode_disabled" || result.code === "wallet_frozen" || result.code === "pin_required" || result.code === "pin_locked") {
      return;
    }
    const me = await session.current();
    if (me.ok && me.data && me.data.role === "retailer") return;
    showGate("login");
    const form = document.getElementById("auth-login");
    if (me.ok && me.data && me.data.role !== "retailer") {
      authError(
        form,
        `Session switched to ${me.data.email} (${me.data.role}) in another tab. Sign in again with a retailer account.`,
      );
    } else {
      authError(form, "Your retailer session ended. Sign in again to continue.");
    }
  }

  function showGate(name) {
    shell.hidden = true;
    gate.hidden = false;
    gate.querySelectorAll("[data-gate]").forEach((card) => {
      card.hidden = card.dataset.gate !== name;
    });
  }

  function authError(form, message) {
    const node = form.querySelector("[data-auth-error]");
    node.hidden = !message;
    node.textContent = message || "";
  }

  async function openCounter(user) {
    appState.user = user || null;
    gate.hidden = true;
    shell.hidden = false;
    if (user && user.email) {
      document.getElementById("who").textContent = user.outlet_name ? `${user.outlet_name} · ${user.email}` : user.email;
      document.getElementById("retailer-name").textContent = user.display_name || user.email;
      const acctEl = document.getElementById("retailer-account-id");
      if (acctEl) acctEl.textContent = user.account_id || "Verified retailer";
      const badgeEl = document.getElementById("kyc-badge");
      if (badgeEl) {
        badgeEl.textContent = user.kyc_verified ? "KYC Verified" : "Retailer";
        badgeEl.classList.toggle("is-verified", !!user.kyc_verified);
      }
    }
    await refreshCoreState();
    route();
    resumePayuReturn(takeStashedPayuReturn() || capturePayuReturn());
    resumeCashfreeReturn();
  }

  document.getElementById("auth-login").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    authError(form, "");
    const result = await session.login(form.email.value, form.password.value);
    if (result.data.mfa_required) return showGate("mfa");
    if (result.data.mfa_setup_required) return showGate("enroll");
    if (result.ok) {
      const me = await session.current();
      return openCounter(me.ok ? me.data : result.data);
    }
    authError(form, result.data.error || "Sign-in failed.");
  });

  document.getElementById("auth-mfa").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    authError(form, "");
    const result = await session.confirmCode(form.code.value);
    if (result.ok) {
      const me = await session.current();
      return openCounter(me.ok ? me.data : result.data);
    }
    authError(form, result.data.error || "Code is incorrect.");
  });

  function scanUri(otpauth) {
    const match = typeof otpauth === "string" ? otpauth.match(/^otpauth:\/\/totp\/([^?]+)\?(.*)$/) : null;
    if (!match) return otpauth || "";
    return "otpauth://totp/" + encodeURIComponent(match[1]) + "?" + match[2];
  }

  document.getElementById("start-enroll").addEventListener("click", async () => {
    const result = await session.beginAuthenticator();
    const box = document.querySelector("[data-enroll-secret]");
    const codes = document.querySelector("[data-enroll-codes]");
    const qr = document.querySelector("[data-enroll-qr]");
    if (!result.ok) {
      authError(document.getElementById("enroll-confirm"), result.data.error || "Could not start setup.");
      return;
    }
    box.hidden = false;
    box.textContent = result.data.secret;
    const drawn = window.drawAuthenticatorQr && drawAuthenticatorQr(document.querySelector("[data-enroll-qr-canvas]"), scanUri(result.data.otpauth));
    qr.hidden = !drawn;
    codes.hidden = false;
    codes.textContent = "Backup codes: " + result.data.backup_codes.join("  ");
  });

  document.getElementById("enroll-confirm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    authError(form, "");
    const result = await session.enableAuthenticator(form.code.value);
    if (result.ok) {
      const me = await session.current();
      return openCounter(me.ok ? me.data : result.data);
    }
    authError(form, result.data.error || "Code is incorrect.");
  });

  document.getElementById("logout").addEventListener("click", async () => {
    await session.signOut();
    showGate("signed-out");
  });

  gate.addEventListener("click", (event) => {
    const reveal = event.target.closest("[data-reveal]");
    if (reveal) {
      const wrap = reveal.closest(".gate-pass");
      const input = wrap && wrap.querySelector("input");
      if (!input) return;
      const shown = input.type === "text";
      input.type = shown ? "password" : "text";
      reveal.setAttribute("aria-label", shown ? "Show password" : "Hide password");
      const icon = reveal.querySelector(".mi");
      if (icon) icon.textContent = shown ? "visibility" : "visibility_off";
      return;
    }
    const jump = event.target.closest("[data-gate-show]");
    if (jump) showGate(jump.dataset.gateShow);
  });

  // PayU redirects here with #wallet?payu=ok|fail — capture before auth/route can strip it.
  const bootPayu = capturePayuReturn();
  if (bootPayu) {
    stashPayuReturn(bootPayu);
    resumePayuReturn(bootPayu);
  }

  session.current().then((me) => {
    if (me.ok && me.data && me.data.role === "retailer") {
      openCounter(me.data);
    } else if (me.ok && me.data && me.data.role !== "retailer") {
      showGate("login");
      authError(
        document.getElementById("auth-login"),
        `Signed in as ${me.data.email} (${me.data.role}). Sign in with a retailer account to use PaySwap.`,
      );
    } else if (me.status === 403 && me.data.mfa_setup_required) {
      showGate("enroll");
    } else {
      showGate("login");
    }
  });
})();
