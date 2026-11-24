(function () {
  const view = document.getElementById("view");
  const crumb = document.getElementById("crumb");
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.querySelector(".backdrop");
  const menuBtn = document.querySelector(".menu-btn");
  const toast = document.getElementById("toast");
  let toastTimer = 0;

  function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, 2800);
  }

  function rupee(value) {
    const amount = Number(String(value).replace(/[^\d.]/g, ""));
    if (!amount) return "";
    return "₹" + amount.toLocaleString("en-IN");
  }

  function slip(rows) {
    return (
      `<p class="kicker">Preview receipt</p>` +
      rows.map(([label, value]) => `<div class="slip-row"><span>${label}</span><strong>${value}</strong></div>`).join("") +
      `<p class="hint">Kept on this counter until the PaySwap retailer API is connected.</p>`
    );
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

  function commission(amount, operator) {
    const rate = /Play|Dish|Sun|Digital/i.test(operator) ? 0.015 : 0.022;
    const value = Number(amount);
    if (!value) return "Enter an amount to see commission";
    return `Est. commission ₹${(value * rate).toFixed(2)}`;
  }

  function refreshAepsSteps(done) {
    const steps = view.querySelectorAll("[data-steps] li");
    if (steps.length < 3) return;
    const ready = (view.querySelector("[name='aadhaar']")?.value || "").length === 12;
    steps[0].className = ready || done ? "is-done" : "is-on";
    steps[1].className = done ? "is-done" : ready ? "is-on" : "";
    steps[2].className = done ? "is-on" : "";
  }

  function show(name) {
    const key = window.Payswap.mount(view, name);
    const title = window.Payswap.titles[key];
    crumb.textContent = title;
    document.title = `${title} · PaySwap`;
    document.querySelectorAll(".nav").forEach((link) => link.classList.toggle("is-on", link.dataset.view === key));
    sidebar.classList.remove("is-open");
    backdrop.hidden = true;
    menuBtn.setAttribute("aria-expanded", "false");
    if (location.hash !== `#${key}`) history.replaceState(null, "", `#${key}`);
  }

  function route() {
    const name = (location.hash || "#home").slice(1) || "home";
    show(name);
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

  view.addEventListener("click", (event) => {
    const choice = event.target.closest("[data-choice]");
    if (choice) {
      choice.parentElement.querySelectorAll("[data-choice]").forEach((button) => button.classList.toggle("is-on", button === choice));
      const mode = view.querySelector("[data-aeps-mode]");
      if (mode) mode.textContent = choice.dataset.choice;
      const amount = view.querySelector("[data-amount-field]");
      if (amount) amount.hidden = choice.dataset.choice !== "Cash withdrawal";
    }

    const bank = event.target.closest("[data-bank]");
    if (bank) {
      view.querySelectorAll("[data-bank]").forEach((item) => item.classList.toggle("is-on", item === bank));
      view.querySelector("[data-aeps-bank]").textContent = bank.dataset.bank;
      view.querySelector("[data-bank-logo]").src = bank.dataset.logo;
      refreshAepsSteps(false);
    }

    const amt = event.target.closest("[data-amt]");
    if (amt) {
      const form = amt.closest("form");
      const input = form.querySelector("[name='amount']");
      input.value = amt.dataset.amt;
      markChips(form, amt.dataset.amt);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }

    const bene = event.target.closest("[data-bene]");
    if (bene) {
      view.querySelectorAll("[data-bene]").forEach((item) => item.classList.toggle("is-on", item === bene));
      const form = view.querySelector("[data-dmt-form]");
      form.name.value = bene.dataset.bene;
      form.ifsc.value = bene.dataset.ifsc;
      form.account.value = bene.dataset.account;
      form.querySelector("[data-dmt-summary]").textContent = `${form.rail.value} to ${bene.dataset.bene}`;
    }

    const op = event.target.closest("[data-op]");
    if (op) {
      view.querySelectorAll("[data-op]").forEach((item) => item.classList.toggle("is-on", item === op));
      view.querySelector("[data-op-name]").textContent = op.dataset.op;
      view.querySelector("[data-op-logo]").src = op.dataset.logo;
      const amount = view.querySelector("[name='amount']");
      view.querySelector("[data-commission]").textContent = commission(amount.value, op.dataset.op);
    }

    const plan = event.target.closest("[data-plan]");
    if (plan) {
      view.querySelectorAll("[data-plan]").forEach((item) => item.classList.toggle("is-on", item === plan));
      const amount = view.querySelector("[name='amount']");
      amount.value = plan.dataset.plan;
      const operator = view.querySelector("[data-op-name]").textContent;
      view.querySelector("[data-commission]").textContent = commission(plan.dataset.plan, operator);
    }

    const biller = event.target.closest("[data-biller]");
    if (biller) {
      view.querySelectorAll("[data-biller]").forEach((item) => item.classList.toggle("is-on", item === biller));
      const form = view.querySelector("[data-bill-form]");
      view.querySelector("[data-bill-empty]").hidden = true;
      form.hidden = false;
      form.querySelector("[data-bill-title]").textContent = biller.dataset.biller;
      form.querySelector("[data-bill-biller]").textContent = biller.dataset.sample;
    }

    const filter = event.target.closest("[data-filter]");
    if (filter) {
      filter.parentElement.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("is-on", item === filter));
      let visible = 0;
      view.querySelectorAll("[data-kind]").forEach((row) => {
        const showRow = filter.dataset.filter === "all" || row.dataset.kind === filter.dataset.filter;
        row.hidden = !showRow;
        if (showRow) visible += 1;
      });
      view.querySelector("[data-filter-empty]").hidden = visible > 0;
    }

    const topic = event.target.closest("[data-topic]");
    if (topic) {
      topic.parentElement.querySelectorAll("[data-topic]").forEach((item) => item.classList.toggle("is-on", item === topic));
      view.querySelector("[name='topic']").value = topic.dataset.topic;
    }
  });

  view.addEventListener("input", (event) => {
    const field = event.target;
    if (field.matches("input, textarea, select")) clearError(field);

    if (field.matches("[data-bank-q]")) {
      const query = field.value.trim().toLowerCase();
      let visible = 0;
      view.querySelectorAll("[data-bank]").forEach((item) => {
        const match = !query || item.dataset.bank.toLowerCase().includes(query);
        item.hidden = !match;
        if (match) visible += 1;
      });
      view.querySelector("[data-bank-empty]").hidden = visible > 0;
    }

    if (field.matches("[data-op-q]")) {
      const query = field.value.trim().toLowerCase();
      let visible = 0;
      view.querySelectorAll("[data-op]").forEach((item) => {
        const match = !query || item.dataset.op.toLowerCase().includes(query);
        item.hidden = !match;
        if (match) visible += 1;
      });
      view.querySelector("[data-op-empty]").hidden = visible > 0;
    }

    if (field.name === "aadhaar") {
      const digits = field.value.replace(/\D/g, "").slice(0, 12);
      field.value = digits;
      view.querySelector("[data-aadhaar-count]").textContent = `${digits.length} / 12`;
      refreshAepsSteps(false);
    }

    if (field.name === "mobile") field.value = field.value.replace(/\D/g, "").slice(0, 10);
    if (field.name === "ifsc") field.value = field.value.toUpperCase();
    if (field.name === "amount" && field.closest("[data-recharge-form]")) {
      view.querySelector("[data-commission]").textContent = commission(field.value, view.querySelector("[data-op-name]").textContent);
      markChips(field.closest("form"), field.value);
    }
    if (field.closest("[data-dmt-form]") && view.querySelector("[data-dmt-summary]")) {
      const form = field.closest("form");
      const who = form.name.value || "beneficiary";
      view.querySelector("[data-dmt-summary]").textContent = `${form.rail.value} to ${who}${form.amount.value ? " · " + rupee(form.amount.value) : ""}`;
    }
  });

  view.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    event.preventDefault();
    const data = new FormData(form);

    if (form.matches("[data-aeps-form]")) {
      const aadhaar = String(data.get("aadhaar") || "");
      if (!/^\d{12}$/.test(aadhaar)) return setError(form.aadhaar, "Enter all 12 digits.");
      const mode = form.querySelector("[data-aeps-mode]").textContent;
      if (mode === "Cash withdrawal") {
        const amount = Number(data.get("amount"));
        if (!amount || amount < 100 || amount > 10000) return setError(form.amount, "Enter ₹100 to ₹10,000.");
      }
      const box = form.querySelector("[data-aeps-receipt]");
      box.hidden = false;
      box.innerHTML = slip([
        ["Service", mode],
        ["Bank", form.querySelector("[data-aeps-bank]").textContent],
        ["Aadhaar", "XXXX XXXX " + aadhaar.slice(-4)],
        ["Amount", mode === "Cash withdrawal" ? rupee(data.get("amount")) : "Enquiry"],
        ["Reference", "PS" + Date.now().toString().slice(-6)],
      ]);
      refreshAepsSteps(true);
      box.scrollIntoView({ block: "nearest" });
      return;
    }

    if (form.matches("[data-dmt-form]")) {
      if (!/^\d{10}$/.test(String(data.get("mobile") || ""))) return setError(form.mobile, "Enter a 10-digit mobile.");
      if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(String(data.get("ifsc") || ""))) return setError(form.ifsc, "Enter a valid IFSC.");
      if (!Number(data.get("amount"))) return setError(form.amount, "Enter an amount.");
      const box = view.querySelector("[data-dmt-receipt]");
      box.hidden = false;
      box.innerHTML = slip([
        ["Rail", data.get("rail")],
        ["Beneficiary", data.get("name")],
        ["Account", data.get("account")],
        ["IFSC", data.get("ifsc")],
        ["Amount", rupee(data.get("amount"))],
      ]);
      return;
    }

    showToast("Saved on this counter. It will post when the PaySwap retailer API is connected.");
  });

  const session = window.PayswapSession;
  const gate = document.getElementById("gate");
  const shell = document.querySelector(".shell");

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

  function openCounter(user) {
    gate.hidden = true;
    shell.hidden = false;
    if (user && user.email) document.getElementById("who").textContent = user.email;
    route();
  }

  gate.addEventListener("click", (event) => {
    const show = event.target.closest("[data-show]");
    if (show) showGate(show.dataset.show);
  });

  document.getElementById("auth-login").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    authError(form, "");
    const result = await session.login(form.email.value, form.password.value);
    if (result.data.mfa_required) return showGate("mfa");
    if (result.data.mfa_setup_required) return showGate("enroll");
    if (result.ok) return openCounter(result.data);
    authError(form, result.data.error || "Sign-in failed.");
  });

  document.getElementById("auth-register").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    authError(form, "");
    const created = await session.register(form.email.value, form.password.value);
    if (!created.ok) return authError(form, created.data.error || "Could not create the account.");
    const result = await session.login(form.email.value, form.password.value);
    if (result.data.mfa_setup_required) return showGate("enroll");
    if (result.data.mfa_required) return showGate("mfa");
    authError(form, result.data.error || "Account saved. Sign in with the existing password.");
  });

  document.getElementById("auth-mfa").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    authError(form, "");
    const result = await session.confirmCode(form.code.value);
    if (result.ok) return openCounter(result.data);
    authError(form, result.data.error || "Code is incorrect.");
  });

  document.getElementById("start-enroll").addEventListener("click", async () => {
    const result = await session.beginAuthenticator();
    const box = document.querySelector("[data-enroll-secret]");
    const codes = document.querySelector("[data-enroll-codes]");
    if (!result.ok) {
      authError(document.getElementById("enroll-confirm"), result.data.error || "Could not start setup.");
      return;
    }
    box.hidden = false;
    box.textContent = result.data.secret;
    codes.hidden = false;
    codes.textContent = "Backup codes: " + result.data.backup_codes.join("  ");
  });

  document.getElementById("enroll-confirm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    authError(form, "");
    const result = await session.enableAuthenticator(form.code.value);
    if (result.ok) return openCounter(result.data);
    authError(form, result.data.error || "Code is incorrect.");
  });

  document.getElementById("logout").addEventListener("click", async () => {
    await session.signOut();
    showGate("login");
  });

  session.current().then((me) => {
    if (me.ok) openCounter(me.data);
    else if (me.status === 403 && me.data.mfa_setup_required) showGate("enroll");
    else showGate("login");
  });
})();
