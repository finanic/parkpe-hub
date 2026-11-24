/* PaySwap counter screens for apps/payswap/index.html.

   AEPS, DMT, recharge, bills, wallet, and transactions stay on this page.
   vouchers() posts through apps/payswap/js/hub.js
   (POST /api/v1/payswap/vouchers/order). Sign-in stays in
   apps/payswap/js/session.js on port 4600 with packages/contracts
   Role.RETAILER (apps/backend/auth/contract.py ROLE_RETAILER).
   Retailer creation stays on the operator console.
   ParkPe must not load this file.
*/
(function () {
  const mk = (id) => `https://static.mobikwik.com/appdata/operator_icons/op${id}.png`;
  const cf = (name) => `https://cashfreelogo.cashfree.com/assets_images/pg/nb/64/${name}.png`;

  const telcos = [
    ["Airtel", mk(1)],
    ["Jio", mk(140)],
    ["Vi", mk(338)],
    ["BSNL", mk(3)],
  ];
  const dth = [
    ["Tata Play", mk(19)],
    ["Airtel Digital TV", mk(23)],
    ["Dish TV", mk(18)],
    ["Sun Direct", mk(22)],
  ];
  const banks = [
    ["State Bank of India", cf("sbi")],
    ["HDFC Bank", cf("hdfc")],
    ["ICICI Bank", cf("icici")],
    ["Axis Bank", cf("axis")],
    ["Bank of Baroda", cf("bobc")],
    ["Punjab National Bank", cf("pnbc")],
  ];
  const txns = [
    { kind: "aeps", icon: "fingerprint", title: "AEPS cash withdrawal", meta: "Aadhaar · SBI · 4:12 pm", amount: "₹2,000", status: "Settled" },
    { kind: "dmt", icon: "send", title: "DMT IMPS", meta: "XXXX4410 · UTR 518922", amount: "₹5,000", status: "Settled" },
    { kind: "recharge", icon: "smartphone", title: "Mobile recharge", meta: "Airtel · 98xxxxxx10", amount: "₹299", status: "Settled" },
    { kind: "bills", icon: "receipt_long", title: "Bill pay", meta: "BSES Rajdhani", amount: "₹1,840", status: "Pending" },
  ];

  function esc(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function icon(name) {
    return `<span class="mi">${name}</span>`;
  }

  function txnList(rows) {
    return rows
      .map(
        (row) => `
        <div class="txn" data-kind="${row.kind}">
          <span class="txn-ico">${icon(row.icon)}</span>
          <div class="txn-copy"><strong>${esc(row.title)}</strong><p>${esc(row.meta)}</p></div>
          <div class="txn-side"><strong>${esc(row.amount)}</strong><span class="pill ${row.status === "Settled" ? "ok" : "wait"}">${esc(row.status)}</span></div>
        </div>`,
      )
      .join("");
  }

  function chips(values, selected) {
    return `<div class="chips">${values
      .map((value) => `<button type="button" class="chip${value === selected ? " is-on" : ""}" data-amt="${value}">₹${Number(value).toLocaleString("en-IN")}</button>`)
      .join("")}</div>`;
  }

  function home() {
    return `
      <div class="screen">
        <header class="hero hero-row">
          <div>
            <p class="kicker">Outlet 1042 · Gurugram</p>
            <h1 id="hello">Counter</h1>
            <p>18 transactions today. One bill is still waiting on the biller.</p>
          </div>
          <a class="btn yellow" href="#bills">Collect a bill</a>
        </header>
        <div class="stats">
          <article class="stat"><span>Float</span><strong>₹48,250</strong><em>₹2,000 held</em></article>
          <article class="stat"><span>Commission today</span><strong>₹1,240</strong><em>Settles into float</em></article>
          <article class="stat"><span>Transactions</span><strong>18</strong><em>17 settled · 1 pending</em></article>
        </div>
        <div class="tiles">
          <a class="tile" href="#aeps">${icon("fingerprint")}<strong>AEPS</strong><p>Cash withdrawal, balance, mini statement.</p></a>
          <a class="tile" href="#dmt">${icon("send")}<strong>DMT</strong><p>IMPS and NEFT from this counter.</p></a>
          <a class="tile" href="#recharge">${icon("smartphone")}<strong>Recharges</strong><p>Prepaid mobile and DTH.</p></a>
          <a class="tile" href="#bills">${icon("receipt_long")}<strong>Bill pay</strong><p>Walk-in bill collection.</p></a>
        </div>
        <section class="card">
          <h2>Latest at this outlet</h2>
          ${txnList(txns)}
        </section>
      </div>`;
  }

  function aeps() {
    const rows = banks
      .map(
        ([name, src], index) =>
          `<button type="button" class="bank${index === 0 ? " is-on" : ""}" data-bank="${esc(name)}" data-logo="${esc(src)}"><span class="mark"><img src="${esc(src)}" alt="" /></span><span>${esc(name)}</span></button>`,
      )
      .join("");
    return `
      <div class="screen">
        <header class="page-head">
          <div>
            <p class="kicker">AEPS</p>
            <h1>Cash at the counter</h1>
          </div>
          <p>Pick the customer bank, enter Aadhaar, then capture the fingerprint when the scanner is paired.</p>
        </header>
        <div class="callout">
          <span class="mi">usb_off</span>
          <div>
            <strong>Biometric device not paired</strong>
            <p>This preview stays on the counter. Nothing is sent until the scanner is connected.</p>
          </div>
        </div>
        <ol class="steps" data-steps>
          <li class="is-on">1 · Bank</li>
          <li>2 · Customer</li>
          <li>3 · Receipt</li>
        </ol>
        <div class="choices">
          <button type="button" class="choice is-on" data-choice="Cash withdrawal">Cash withdrawal</button>
          <button type="button" class="choice" data-choice="Balance enquiry">Balance enquiry</button>
          <button type="button" class="choice" data-choice="Mini statement">Mini statement</button>
        </div>
        <div class="split">
          <section class="card">
            <h2>Customer bank</h2>
            <input class="search" data-bank-q type="search" placeholder="Search bank" aria-label="Search bank" />
            <div class="ops">${rows}</div>
            <p class="empty-note" data-bank-empty hidden>No bank matches that search.</p>
          </section>
          <form class="card fields panel" data-aeps-form>
            <div class="picked">
              <span class="mark"><img src="${banks[0][1]}" alt="" data-bank-logo /></span>
              <div>
                <p class="kicker" data-aeps-mode>Cash withdrawal</p>
                <strong data-aeps-bank>State Bank of India</strong>
              </div>
            </div>
            <label class="field">Aadhaar number
              <input name="aadhaar" inputmode="numeric" autocomplete="off" maxlength="12" required placeholder="12 digits" />
              <span class="count" data-aadhaar-count>0 / 12</span>
            </label>
            <div data-amount-field>
              <span class="hint">Amount</span>
              ${chips(["500", "1000", "2000", "5000", "10000"], "")}
              <label class="field">Other amount<input name="amount" inputmode="decimal" placeholder="₹ 2,000" /></label>
            </div>
            <p class="hint">Cash withdrawal on this preview is ₹100 to ₹10,000.</p>
            <button class="btn yellow block" type="submit">Capture fingerprint</button>
            <div class="receipt" data-aeps-receipt hidden></div>
          </form>
        </div>
      </div>`;
  }

  function dmt() {
    const people = [
      ["Household account", "SBIN0000451", "XXXX4410"],
      ["Family account", "HDFC0000123", "XXXX9081"],
    ];
    return `
      <div class="screen">
        <header class="page-head">
          <div>
            <p class="kicker">Domestic transfer</p>
            <h1>Send from float</h1>
          </div>
          <p>Confirm the sender, pick a saved beneficiary or type a new account, then choose IMPS or NEFT.</p>
        </header>
        <div class="split">
          <section class="card">
            <h2>Saved beneficiaries</h2>
            ${people
              .map(
                ([name, ifsc, account]) => `
              <button type="button" class="bank" data-bene="${esc(name)}" data-ifsc="${esc(ifsc)}" data-account="${esc(account)}">
                <span class="txn-ico">${icon("account_balance")}</span>
                <span><strong>${esc(name)}</strong><p>${esc(ifsc)} · ${esc(account)}</p></span>
              </button>`,
              )
              .join("")}
          </section>
          <form class="card fields panel" data-dmt-form>
            <label class="field">Sender mobile<input name="mobile" inputmode="numeric" maxlength="10" required placeholder="10-digit mobile" /></label>
            <label class="field">Rail
              <select name="rail"><option>IMPS</option><option>NEFT</option></select>
            </label>
            <label class="field">Beneficiary name<input name="name" required placeholder="Account holder" /></label>
            <label class="field">Account number<input name="account" required placeholder="Account number" /></label>
            <label class="field">IFSC<input name="ifsc" required placeholder="SBIN0000451" autocapitalize="characters" /></label>
            <span class="hint">Amount</span>
            ${chips(["1000", "2000", "5000", "10000"], "5000")}
            <label class="field">Other amount<input name="amount" value="5000" inputmode="decimal" required /></label>
            <p class="hint" data-dmt-summary>IMPS · amount not confirmed yet</p>
            <button class="btn yellow block" type="submit">Send transfer</button>
            <div class="receipt" data-dmt-receipt hidden></div>
          </form>
        </div>
      </div>`;
  }

  function recharge() {
    const rows = [...telcos, ...dth]
      .map(
        ([name, src], index) =>
          `<button type="button" class="op logo-card${index === 0 ? " is-on" : ""}" data-op="${esc(name)}" data-logo="${esc(src)}"><span class="mark"><img src="${esc(src)}" alt="" /></span><span>${esc(name)}</span></button>`,
      )
      .join("");
    return `
      <div class="screen">
        <header class="page-head">
          <div>
            <p class="kicker">Recharge</p>
            <h1>Mobile and DTH</h1>
          </div>
          <p>Choose the operator, enter the number, then pick a plan. Commission shows before you confirm.</p>
        </header>
        <div class="split">
          <section class="card">
            <h2>Operator</h2>
            <input class="search" data-op-q type="search" placeholder="Search operator" aria-label="Search operator" />
            <div class="ops grid">${rows}</div>
            <p class="empty-note" data-op-empty hidden>No operator matches that search.</p>
          </section>
          <form class="card fields panel" data-recharge-form>
            <div class="picked">
              <span class="mark"><img src="${telcos[0][1]}" alt="" data-op-logo /></span>
              <div><strong data-op-name>Airtel</strong><p data-commission>Est. commission ₹6.58</p></div>
            </div>
            <label class="field">Mobile or subscriber ID<input name="account" required placeholder="98xxxxxx10" /></label>
            <div class="plans">
              <button type="button" class="plan" data-plan="149">₹149<small>28 days · 1 GB/day</small></button>
              <button type="button" class="plan is-on" data-plan="299">₹299<small>28 days · 1.5 GB/day</small></button>
              <button type="button" class="plan" data-plan="666">₹666<small>84 days · 1.5 GB/day</small></button>
            </div>
            <label class="field">Amount<input name="amount" value="299" required /></label>
            <button class="btn yellow block" type="submit">Recharge</button>
          </form>
        </div>
      </div>`;
  }

  function bills() {
    const items = [
      ["Electricity", "bolt", "BSES Rajdhani"],
      ["Water", "water_drop", "Delhi Jal Board"],
      ["Piped gas", "local_fire_department", "Indraprastha Gas"],
      ["DTH", "live_tv", "Tata Play"],
      ["Postpaid", "smartphone", "Airtel Postpaid"],
      ["Loan", "payments", "Bajaj Finance"],
    ];
    return `
      <div class="screen">
        <header class="page-head">
          <div>
            <p class="kicker">Bill pay</p>
            <h1>Collect a bill</h1>
          </div>
          <p>Pick a category. The consumer number and amount open on the right.</p>
        </header>
        <div class="split">
          <div class="tiles">
            ${items
              .map(
                ([label, glyph, biller]) => `
              <button type="button" class="tile" data-biller="${esc(label)}" data-sample="${esc(biller)}">
                ${icon(glyph)}<strong>${esc(label)}</strong><p>${esc(biller)}</p>
              </button>`,
              )
              .join("")}
          </div>
          <div class="panel">
            <section class="card" data-bill-empty>
              <h2>Choose a category</h2>
              <p>The form stays closed until a category is selected, so the wrong biller is harder to pay.</p>
            </section>
            <form class="card fields" data-bill-form hidden>
              <h2 data-bill-title>Bill</h2>
              <p data-bill-biller></p>
              <label class="field">Consumer number<input name="account" required placeholder="From the bill" /></label>
              <label class="field">Amount<input name="amount" inputmode="decimal" required placeholder="₹" /></label>
              <button class="btn yellow block" type="submit">Collect payment</button>
            </form>
          </div>
        </div>
      </div>`;
  }

  function wallet() {
    return `
      <div class="screen">
        <header class="page-head">
          <div>
            <p class="kicker">Float</p>
            <h1>Outlet wallet</h1>
          </div>
          <p>Load float before cash-out and transfers. Commission lands in the same wallet.</p>
        </header>
        <div class="stats">
          <article class="stat"><span>Available</span><strong>₹48,250</strong><em>Ready to use</em></article>
          <article class="stat"><span>Held</span><strong>₹2,000</strong><em>AEPS in progress</em></article>
          <article class="stat"><span>Commission MTD</span><strong>₹18,640</strong><em>This month</em></article>
        </div>
        <section class="card">
          <div class="meter-copy"><span>Used today</span><span>₹21,750 of ₹70,000</span></div>
          <div class="meter" aria-hidden="true"><span style="width:31%"></span></div>
        </section>
        <form class="card fields" data-wallet-form>
          <h2>Add float</h2>
          ${chips(["5000", "10000", "25000"], "10000")}
          <label class="field">Amount<input name="amount" value="10000" required /></label>
          <label class="field">From
            <select name="from"><option>Current account</option><option>UPI</option></select>
          </label>
          <button class="btn yellow" type="submit">Request load</button>
        </form>
      </div>`;
  }

  function transactions() {
    return `
      <div class="screen">
        <header class="page-head">
          <div>
            <p class="kicker">Transactions</p>
            <h1>Outlet book</h1>
          </div>
          <p>Filter by service. Pending items stay visible until the biller confirms.</p>
        </header>
        <div class="filters">
          <button type="button" class="chip is-on" data-filter="all">All</button>
          <button type="button" class="chip" data-filter="aeps">AEPS</button>
          <button type="button" class="chip" data-filter="dmt">DMT</button>
          <button type="button" class="chip" data-filter="recharge">Recharges</button>
          <button type="button" class="chip" data-filter="bills">Bills</button>
        </div>
        <section class="card">${txnList(txns)}<p class="empty-note" data-filter-empty hidden>Nothing in this filter.</p></section>
      </div>`;
  }

  function support() {
    const topics = ["AEPS device", "DMT failed", "Float not credited", "Recharge pending"];
    return `
      <div class="screen">
        <header class="page-head">
          <div>
            <p class="kicker">Support</p>
            <h1>Ask the counter desk</h1>
          </div>
          <p>Pick a topic and add the transaction reference if you have one.</p>
        </header>
        <form class="card fields" data-support-form>
          <input type="hidden" name="topic" value="AEPS device" />
          <div class="choices">
            ${topics.map((topic, index) => `<button type="button" class="choice${index === 0 ? " is-on" : ""}" data-topic="${esc(topic)}">${esc(topic)}</button>`).join("")}
          </div>
          <label class="field">Reference<input name="ref" placeholder="Transaction id" /></label>
          <label class="field">What happened<textarea name="note" rows="4" required placeholder="Short note from the counter"></textarea></label>
          <button class="btn yellow" type="submit">Send</button>
        </form>
      </div>`;
  }

  function vouchers() {
    return `
      <div class="screen">
        <header class="page-head">
          <div>
            <p class="kicker">Vouchers</p>
            <h1>Brand voucher</h1>
          </div>
          <p>Starts the order on the hub. Sign-in for this counter stays on port 4600.</p>
        </header>
        <form class="card fields" data-voucher-form>
          <label class="field">Brand<input name="brand" required placeholder="Amazon" autocomplete="off" /></label>
          <label class="field">Amount<input name="amount" inputmode="decimal" required placeholder="100.00" /></label>
          <button class="btn yellow" type="submit">Order voucher</button>
          <p class="hint" data-voucher-status hidden></p>
        </form>
      </div>`;
  }

  const screens = { home, aeps, dmt, recharge, bills, vouchers, wallet, transactions, support };
  const titles = {
    home: "Home",
    aeps: "AEPS",
    dmt: "DMT",
    recharge: "Recharges",
    bills: "Bill pay",
    vouchers: "Vouchers",
    wallet: "Float",
    transactions: "Transactions",
    support: "Support",
  };

  window.Payswap = {
    screens,
    titles,
    mount(root, name) {
      const key = screens[name] ? name : "home";
      root.innerHTML = screens[key]();
      const hello = root.querySelector("#hello");
      if (hello) {
        const hour = new Date().getHours();
        hello.textContent = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
      }
      return key;
    },
  };
})();
