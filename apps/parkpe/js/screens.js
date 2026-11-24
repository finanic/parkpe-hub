(function () {
const I = {
  utility: "M13 2 6 13h5l-1 9 8-13h-6l1-7Z",
  mobile: "M8 3h8a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm3 15h2M9 7h6M9 11h6M9 15h3",
  dth: "M12 17v4M8 21h8M5 13a7 7 0 0 1 14 0M8 13a4 4 0 0 1 8 0M12 13h.01M4 5l16 14",
  cable: "M4 7h16v11H4V7Zm5-4 3 4 3-4M8 21h8",
  water: "M12 3s6 6.2 6 11a6 6 0 0 1-12 0c0-4.8 6-11 6-11Z",
  gas: "M4 17h16M6 17v-5a6 6 0 0 1 12 0v5M9 17v4M15 17v4M12 7v4",
  broadband: "M4 13a8 8 0 0 1 16 0M7 16a5 5 0 0 1 10 0M10 19a2 2 0 0 1 4 0M5 21h14",
  insurance: "M12 22s8-4 8-10V5l-8 3-8 3v7c0 6 8 10 8 10Z",
  loan: "M4 17h16M7 17v-5h10v5M9 12V8h6v4M12 3v5M8 6h8",
  education: "M4 10 12 5l8 5-8 5-8-5Zm4 3v4c0 1.7 8 1.7 8 0v-4M20 10v6",
  municipality: "M5 21V8l7-5 7 5v13M9 21v-7h6v7M8 10h.01M12 10h.01M16 10h.01",
  credit: "M3 6h18v12H3V6Zm0 4h18M7 15h4M15 15h2",
  cylinder: "M9 3h6M10 6h4M8 9h8v10a3 3 0 0 1-3 3h-2a3 3 0 0 1-3-3V9Z",
  landline: "M4 9h16v11H4V9Zm3 3h10M8 17h2M14 17h2",
  hospital: "M3 21h18M5 21V10l7-4 7 4v11M9 21v-4h6v4M9 14h6",
  home: "M3 10.5 12 3l9 7.5V21H3V10.5Zm6 0V21h6v-6H9v6",
  club: "M17 21v-8M7 21v-8M12 8l9 4-9 4-9-4 9-4Zm0 0v8",
  chart: "M3 3v18h18M7 16l4-8 4 5 4-10",
  piggy: "M19 5c-1.5 0-3 1.2-3 3s1.5 3 3 3 3-1.2 3-3-1.5-3-3-3ZM5 21h14M5 21c0-4 4-7 7-7s7 3 7 7",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z",
  receipt: "M4 2h16v20l-4-2-4 2-4-2-4 2V2Z",
};

const billGroups = [
  {
    label: "Recharges & telecom",
    items: [
      ["Prepaid Mobile", I.mobile],
      ["Postpaid Mobile", I.mobile],
      ["DTH", I.dth],
      ["Cable TV", I.cable],
      ["Broadband", I.broadband],
      ["Landline", I.landline],
    ],
  },
  {
    label: "Utilities & daily",
    items: [
      ["Electricity", I.utility],
      ["Water", I.water],
      ["Piped Gas", I.gas],
      ["LPG Booking", I.cylinder],
      ["Municipality", I.municipality],
      ["Education Fee", I.education],
      ["Housing Society", I.home],
      ["Hospitals & Pathology", I.hospital],
    ],
  },
  {
    label: "Finance, insurance & investments",
    items: [
      ["Loan Repayment", I.loan],
      ["Credit Card", I.credit],
      ["Insurance", I.insurance],
      ["Health Insurance", I.shield],
      ["Mutual Funds", I.chart],
      ["NPS", I.piggy],
      ["Recurring Deposit", I.piggy],
      ["EMI / Loan EMI", I.receipt],
      ["Clubs & Associations", I.club],
    ],
  },
];

const mk = (id) => `https://static.mobikwik.com/appdata/operator_icons/op${id}.png`;
const cf = (mode, name) => `https://cashfreelogo.cashfree.com/assets_images/pg/${mode}/64/${name}.png`;
const mark = (domain) => `https://www.google.com/s2/favicons?domain=${domain}&sz=128`;

const operatorLogos = {
  "Airtel Prepaid": mk(1),
  Jio: mk(140),
  Vi: mk(338),
  BSNL: mk(3),
  MTNL: mk(7),
  "Airtel Postpaid": mk(29),
  "Jio Postpaid": mk(142),
  "Vi Postpaid": mk(436),
  "BSNL Postpaid": mk(34),
  "Tata Play": mk(19),
  "Airtel Digital TV": mk(23),
  "Dish TV": mk(18),
  d2h: mk(21),
  "Sun Direct": mk(22),
  Hathway: mk(135),
  "DEN Networks": mk(1467),
  "Siti Networks": mark("sitinetworks.com"),
  GTPL: mk(675),
  "Asianet Digital": mk(435),
  "Airtel Xstream": mk(214),
  JioFiber: mk(140),
  "ACT Fibernet": mk(129),
  Excitel: mark("excitel.com"),
  "Hathway Broadband": mk(135),
  "BSNL Landline": mk(131),
  "Airtel Landline": mk(28),
  "MTNL Delhi": mk(40),
  "MTNL Mumbai": mk(133),
  "BSES Rajdhani": mk(32),
  "BSES Yamuna": mk(33),
  "Tata Power DDL": mk(41),
  "Tata Power": mk(146),
  MSEDCL: mk(39),
  "Adani Electricity": mk(31),
  BESCOM: mk(67),
  TNEB: mk(189),
  UPPCL: mk(1743),
  "Delhi Jal Board": mk(262),
  "BMC Water": mark("mcgm.gov.in"),
  BWSSB: mk(70),
  HMWSSB: mk(211),
  "Kerala Water Authority": mk(298),
  "Indraprastha Gas": mk(65),
  "Mahanagar Gas": mk(38),
  "Adani Total Gas": mk(126),
  "Gujarat Gas": mk(66),
  Indane: mk(293),
  "Bharat Gas": mk(897),
  "HP Gas": mk(978),
  "MCD Property Tax": mk(1771),
  NDMC: mk(218),
  "BMC Property Tax": mark("mcgm.gov.in"),
  GHMC: mk(863),
  CBSE: mark("cbse.gov.in"),
  "Delhi University": mark("du.ac.in"),
  "School fee": mark("cbse.gov.in"),
  "College fee": mark("du.ac.in"),
  MyGate: mark("mygate.com"),
  NoBrokerHood: mark("nobroker.in"),
  ApnaComplex: mark("apnacomplex.com"),
  "Apollo Hospitals": mark("apollohospitals.com"),
  "Max Healthcare": mark("maxhealthcare.in"),
  "Dr Lal PathLabs": mark("lalpathlabs.com"),
  "SRL Diagnostics": mark("srlworld.com"),
  "HDFC Ltd": cf("nb", "hdfc"),
  "Bajaj Finance": mk(388),
  "LIC Housing Finance": mark("lichousing.com"),
  "Tata Capital": mk(304),
  "HDFC Bank Credit Card": cf("nb", "hdfc"),
  "SBI Card": cf("nb", "sbi"),
  "ICICI Bank Credit Card": cf("nb", "icici"),
  "Axis Bank Credit Card": cf("nb", "axis"),
  LIC: mark("licindia.in"),
  "HDFC Life": mk(285),
  "ICICI Prudential": mk(37),
  "SBI Life": mk(134),
  "Star Health": mk(693),
  "Niva Bupa": mk(417),
  "Care Health": mark("careinsurance.com"),
  "HDFC Ergo": mk(1332),
  "HDFC Mutual Fund": cf("nb", "hdfc"),
  "SBI Mutual Fund": cf("nb", "sbi"),
  "ICICI Prudential MF": cf("nb", "icici"),
  "NSDL NPS": mark("nsdl.co.in"),
  "KFintech NPS": mark("kfintech.com"),
  "SBI RD": cf("nb", "sbi"),
  "HDFC Bank RD": cf("nb", "hdfc"),
  "Post Office RD": mark("indiapost.gov.in"),
  "Bajaj Finserv EMI": mk(388),
  "HDFC EMI": cf("nb", "hdfc"),
  "IDFC FIRST EMI": cf("nb", "idfc"),
  "Club membership": mark("india.gov.in"),
  "Association fee": mark("india.gov.in"),
};

const operators = {
  "Prepaid Mobile": ["Airtel Prepaid", "Jio", "Vi", "BSNL", "MTNL"],
  "Postpaid Mobile": ["Airtel Postpaid", "Jio Postpaid", "Vi Postpaid", "BSNL Postpaid"],
  DTH: ["Tata Play", "Airtel Digital TV", "Dish TV", "d2h", "Sun Direct"],
  "Cable TV": ["Hathway", "DEN Networks", "Siti Networks", "GTPL", "Asianet Digital"],
  Broadband: ["Airtel Xstream", "JioFiber", "ACT Fibernet", "Excitel", "Hathway Broadband"],
  Landline: ["BSNL Landline", "Airtel Landline", "MTNL Delhi", "MTNL Mumbai"],
  Electricity: ["BSES Rajdhani", "BSES Yamuna", "Tata Power DDL", "Tata Power", "MSEDCL", "Adani Electricity", "BESCOM", "TNEB", "UPPCL"],
  Water: ["Delhi Jal Board", "BMC Water", "BWSSB", "HMWSSB", "Kerala Water Authority"],
  "Piped Gas": ["Indraprastha Gas", "Mahanagar Gas", "Adani Total Gas", "Gujarat Gas"],
  "LPG Booking": ["Indane", "Bharat Gas", "HP Gas"],
  Municipality: ["MCD Property Tax", "NDMC", "BMC Property Tax", "GHMC"],
  "Education Fee": ["CBSE", "Delhi University", "School fee", "College fee"],
  "Housing Society": ["MyGate", "NoBrokerHood", "ApnaComplex"],
  "Hospitals & Pathology": ["Apollo Hospitals", "Max Healthcare", "Dr Lal PathLabs", "SRL Diagnostics"],
  "Loan Repayment": ["HDFC Ltd", "Bajaj Finance", "LIC Housing Finance", "Tata Capital"],
  "Credit Card": ["HDFC Bank Credit Card", "SBI Card", "ICICI Bank Credit Card", "Axis Bank Credit Card"],
  Insurance: ["LIC", "HDFC Life", "ICICI Prudential", "SBI Life"],
  "Health Insurance": ["Star Health", "Niva Bupa", "Care Health", "HDFC Ergo"],
  "Mutual Funds": ["HDFC Mutual Fund", "SBI Mutual Fund", "ICICI Prudential MF"],
  NPS: ["NSDL NPS", "KFintech NPS"],
  "Recurring Deposit": ["SBI RD", "HDFC Bank RD", "Post Office RD"],
  "EMI / Loan EMI": ["Bajaj Finserv EMI", "HDFC EMI", "IDFC FIRST EMI"],
  "Clubs & Associations": ["Club membership", "Association fee"],
};

const fastagIssuers = [
  ["ICICI Bank", "icici-bank.png"],
  ["HDFC Bank", "hdfc-bank.png"],
  ["State Bank of India FASTag", "sbi.png"],
  ["Axis Bank", "axis-bank.png"],
  ["Kotak Mahindra Bank", "kotak-mahindra-bank.png"],
  ["IDFC FIRST Bank - FasTag", "idfc-first-bank.png"],
  ["Airtel Payments Bank NETC FASTag", "airtel-payments-bank.png"],
  ["IndusInd Bank", "indusind-bank.png"],
  ["Bank of Baroda", "bank-of-baroda.png"],
  ["Yes Bank FASTag", "yes-bank.png"],
  ["IDBI Bank FASTag", "idbi-bank.png"],
  ["Indian Bank Fastag", "indian-bank.png"],
  ["Canara Bank Fastag", "canara-bank.png"],
  ["Union Bank of India Fastag", "union-bank.png"],
  ["Bank of Maharashtra Fastag", "bank-of-maharashtra.png"],
  ["Federal Bank - FASTag", "federal-bank.png"],
  ["AU Bank Fastag", "au-bank.png"],
  ["Bandhan Bank Fastag", "bandhan-bank.png"],
  ["Equitas FASTag Recharge", "equitas-bank.png"],
  ["Bajaj Finance Limited Fastag", "bajaj-finance.png"],
  ["Paytm Payments Bank", ""],
];
const brands = [
  ["Amazon", "Shopping", "8%"],
  ["Flipkart", "Shopping", "7%"],
  ["Swiggy", "Food", "10%"],
  ["Zomato", "Food", "9%"],
  ["Myntra", "Fashion", "12%"],
  ["BookMyShow", "Entertainment", "6%"],
  ["Uber", "Travel", "5%"],
  ["Starbucks", "Food", "8%"],
];

function icon(name) {
  return `<span class="mi">${name}</span>`;
}

function esc(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function hero(kicker, title, lead) {
  return `<header class="screen-hero"><a class="round-back" href="#dashboard" aria-label="Back to dashboard"><span class="mi">arrow_back</span></a><div><p class="screen-kicker">${kicker}</p><h1>${title}</h1><p>${lead}</p></div></header>`;
}

function opRow(name, options) {
  const on = options && options.on;
  const logo = options && options.logo;
  const mark = logo
    ? `<span class="op-mark"><img src="${esc(logo)}" alt="" /></span>`
    : `<span class="op-mark">${esc(name.trim().charAt(0) || "?")}</span>`;
  return `<button type="button" class="op-row${on ? " is-on" : ""}" data-op="${esc(name)}">${mark}<span class="op-name">${esc(name)}</span><span class="mi op-chev">chevron_right</span></button>`;
}

function field(label, control) {
  return `<label class="field"><span>${label}</span>${control}</label>`;
}

function tileIcon(path) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path}"/></svg>`;
}

function billScreen() {
  const count = billGroups.reduce((sum, group) => sum + group.items.length, 0);
  const groups = billGroups
    .map(
      (group, index) => `
      <section class="bbps-group" data-bill-group ${index ? "" : ""}>
        <h2>${group.label}</h2>
        <div class="bbps-tiles">
          ${group.items
            .map(
              ([label, path]) => `
            <button type="button" class="bbps-tile" data-bill="${esc(label)}">
              <span class="bbps-ico">${tileIcon(path)}</span>
              <span>${esc(label)}</span>
            </button>`,
            )
            .join("")}
        </div>
      </section>`,
    )
    .join("");
  return `
    <div class="bbps" data-screen="bill-payments">
      <section class="bbps-card" data-bill-stage="grid">
        <header class="bbps-head">
          <div class="bbps-title">
            <a class="bbps-back" href="#dashboard" aria-label="Back to dashboard">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            </a>
            <div>
              <h1>Bill Payment Categories</h1>
              <p>Showing categories from your Bharat BillPay catalogue (${count} enabled).</p>
            </div>
          </div>
          <img class="bbps-logo" src="../assets/img/bharat-connect.png" alt="Bharat Connect" width="160" height="44" />
        </header>
        <div class="bbps-body">
          <label class="bbps-search">
            <span class="sr-only">Search billers or categories</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z"/></svg>
            <input type="search" data-bill-search placeholder="Search billers or categories..." />
          </label>
          ${groups}
          <p class="bbps-empty" data-bill-empty hidden>No matching bill categories found.</p>
        </div>
      </section>
      <aside class="bbps-side" data-bill-side>
        <section class="bbps-panel">
          <div class="bbps-panel-head">
            <h2>Recent payments</h2>
            <a href="#transactions">View all</a>
          </div>
          <ul class="bbps-recent">
            <li>
              <button type="button">
                <span><strong>Electricity</strong><small>BSES Rajdhani · 18 Nov 2026</small></span>
                <span class="bbps-amt">₹2,140 <em>Paid</em></span>
              </button>
            </li>
            <li>
              <button type="button">
                <span><strong>Prepaid Mobile</strong><small>Airtel Prepaid · 16 Nov 2026</small></span>
                <span class="bbps-amt">₹299 <em>Paid</em></span>
              </button>
            </li>
          </ul>
          <p class="bbps-hint">Tap a row to view receipt details when available.</p>
        </section>
        <section class="bbps-panel">
          <div class="bbps-panel-head">
            <h2>General Knowledge</h2>
            <span class="bbps-info" aria-hidden="true">i</span>
          </div>
          <div class="bbps-notes">
            <article>
              <h3>Variety of online Bill Payments and e-Services</h3>
              <ul>
                <li>Pay your electricity, water and Utility bills online without any hassle and avoid late payment charges</li>
                <li>Recharge your mobile, landline, cable and DTH devices in few clicks</li>
                <li>Loan and Insurance services made easy through one click easy payments.</li>
              </ul>
            </article>
            <article>
              <h3>General Instructions:</h3>
              <ul>
                <li>It is recommended to wait for 48 hours before re-trying the bill payments for same consumer number. Pay your bills before due date to avoid penalty.</li>
                <li>Keep the receipt or transaction ID for future support.</li>
                <li>Pay bills before due date to avoid penalty charges.</li>
                <li>You can download the receipts at any time from the portal and export transaction history into Excel file.</li>
                <li>If biller reject/refund the transaction, then the amount is refunded to the customer.</li>
              </ul>
            </article>
            <article class="is-dark">
              <h3>Retailer Note</h3>
              <p>For failed or pending payments, ask customers to wait for bank confirmation before retrying the same bill.</p>
            </article>
          </div>
        </section>
      </aside>
      <section class="bbps-card" data-bill-stage="ops" hidden></section>
    </div>`;
}

function billOps(category) {
  const names = operators[category] || ["Operator"];
  const rows = names
    .map((name, index) => opRow(name, { on: index === 0, logo: operatorLogos[name] || "" }))
    .join("");
  const first = names[0];
  const firstLogo = operatorLogos[first] || "";
  const firstMark = firstLogo
    ? `<img src="${esc(firstLogo)}" alt="" data-op-logo />`
    : esc(first.charAt(0));
  return `
    <header class="sheet-head">
      <button class="round-back" type="button" data-bill-back aria-label="All categories"><span class="mi">arrow_back</span></button>
      <div>
        <h1>${esc(category)}</h1>
        <p>Secured Bharat BillPay workflow</p>
      </div>
    </header>
    <div class="steps">
      <span class="step is-on" data-step="details">1. Details</span>
      <span class="step" data-step="bill">2. Bill</span>
      <span class="step" data-step="pay">3. Pay</span>
      <span class="step" data-step="done">4. Done</span>
    </div>
    <div class="op-layout">
      <div class="op-board">
        <header>
          <strong>Billers — ${esc(category)}</strong>
          <p>Search and select your biller</p>
        </header>
        <input class="field-input op-search" type="search" data-op-search placeholder="Search your operator" />
        <div class="op-list" data-op-list>${rows}</div>
      </div>
      <form class="screen-panel form-grid op-detail" data-bill-form>
        <p class="screen-kicker">Account details</p>
        <div class="op-selected">
          <span class="op-mark" data-op-mark>${firstMark}</span>
          <div>
            <h2 data-op-current>${esc(first)}</h2>
            <p>${esc(category)}</p>
          </div>
        </div>
        ${field("Consumer number", `<input name="account" required placeholder="Enter consumer number" />`)}
        <p class="empty-copy">This must match the number on the physical bill.</p>
        <button class="btn-dark" type="submit">Fetch bill</button>
        <div class="due-card" data-bill-due hidden>
          <span>Amount due</span>
          <strong>₹2,140</strong>
          <p data-due-account></p>
          <button class="btn-dark" type="button" data-bill-pay>Pay ₹2,140</button>
        </div>
      </form>
    </div>`;
}

function fastagScreen() {
  const rows = fastagIssuers
    .map(([name, file], index) =>
      opRow(name, {
        on: index === 0,
        logo: file ? `../assets/img/fastag-issuers/${file}` : cf("wallet", "paytm"),
      }),
    )
    .join("");
  return `
    <section class="sheet">
      <header class="sheet-head">
        <a class="round-back" href="#dashboard" aria-label="Back to dashboard"><span class="mi">arrow_back</span></a>
        <div>
          <p class="screen-kicker">Retailer service</p>
          <h1>FASTag recharge</h1>
          <p>Select the issuer, then enter the vehicle number.</p>
        </div>
      </header>
      <div class="steps">
        <span class="step is-on">1. Issuer</span>
        <span class="step">2. Vehicle</span>
        <span class="step">3. Recharge</span>
      </div>
      <div class="op-layout">
        <div class="op-board">
          <header>
            <strong>Operators — FASTag issuers</strong>
            <p>${fastagIssuers.length} issuers · search your bank</p>
          </header>
          <input class="field-input op-search" type="search" data-op-search placeholder="Search your FASTag bank" />
          <div class="op-list">${rows}</div>
        </div>
        <form class="screen-panel form-grid op-detail">
          <p class="screen-kicker">Vehicle and issuer</p>
          <div class="op-selected">
            <span class="op-mark"><img src="../assets/img/fastag-issuers/icici-bank.png" alt="" data-op-logo /></span>
            <div>
              <h2 data-op-current>ICICI Bank</h2>
              <p>FASTag issuer</p>
            </div>
          </div>
          ${field("Vehicle number", `<input name="vehicle" required value="DL 01 AB 1234" />`)}
          ${field("Amount", `<input name="amount" inputmode="decimal" required placeholder="₹ 500" />`)}
          <button class="btn-dark" type="submit">Recharge FASTag</button>
        </form>
      </div>
    </section>`;
}

function challanScreen() {
  return `
    <div class="screen">
      ${hero("Traffic services", "Traffic challans", "Check a vehicle and pay the challans that are still open.")}
      <form class="screen-panel form-row" data-challan-form>
        ${field("Vehicle number", `<input name="vehicle" required placeholder="DL 01 AB 1234" />`)}
        <button class="btn-dark" type="submit">Check challans</button>
      </form>
      <div class="stack" data-challan-results hidden></div>
    </div>`;
}

function qrScreen() {
  return `
    <div class="screen screen-narrow">
      ${hero("Connect QR", "Scan & pay", "Paste a ParkPe QR link, parking slip token, or CoPilot trip code.")}
      <form class="screen-panel form-grid">
        <label class="field"><span>QR content</span><textarea name="payload" rows="4" required placeholder="Paste QR content or URL"></textarea></label>
        <button class="btn-dark" type="submit">Resolve QR</button>
      </form>
      <div class="screen-panel" data-qr-result hidden></div>
    </div>`;
}

function voucherScreen() {
  return `
    <div class="screen">
      ${hero("ParkPe voucher", "ParkPe vouchers", "Buy a voucher, link one you already have, or check a balance.")}
      <div class="tabs">
        <button type="button" class="tab is-on" data-tab="mine">My vouchers</button>
        <button type="button" class="tab" data-tab="buy">Buy</button>
        <button type="button" class="tab" data-tab="link">Link</button>
      </div>
      <div data-panel="mine" class="stack">
        <article class="voucher-card"><div><strong>PP-20481</strong><p>Balance ₹1,250 · Expires 12 Aug 2027</p></div><span class="status status-paid">Active</span></article>
        <article class="voucher-card"><div><strong>PP-19802</strong><p>Balance ₹0 · Used at Cyber Hub</p></div><span class="status status-due">Used</span></article>
      </div>
      <form data-panel="buy" class="screen-panel form-grid" hidden>
        ${field("Amount", `<input name="amount" required placeholder="₹ 1,000" />`)}
        ${field("Send to", `<input name="mobile" required placeholder="Mobile number" />`)}
        <button class="btn-dark" type="submit">Create voucher</button>
      </form>
      <form data-panel="link" class="screen-panel form-grid" hidden>
        ${field("Voucher code", `<input name="code" required placeholder="PP-00000" />`)}
        <button class="btn-dark" type="submit">Link voucher</button>
      </form>
    </div>`;
}

function brandScreen() {
  const cards = brands
    .map(
      ([name, category, off]) => `
      <article class="brand-card" data-brand="${name}" data-category="${category}">
        <span class="brand-mark">${name.slice(0, 1)}</span>
        <strong>${name}</strong>
        <p>${category}</p>
        <span class="chip">Up to ${off}</span>
      </article>`,
    )
    .join("");
  return `
    <div class="screen">
      ${hero("Brand vouchers", "Buy vouchers", "8 brands · save up to 12%.")}
      <input class="field-input" type="search" data-brand-search placeholder="Search by brand name" />
      <div class="tabs">
        ${["All", "Shopping", "Food", "Fashion", "Entertainment", "Travel"].map((item, index) => `<button type="button" class="tab ${index === 0 ? "is-on" : ""}" data-brand-filter="${item}">${item}</button>`).join("")}
      </div>
      <div class="brand-grid">${cards}</div>
    </div>`;
}

function carpoolScreen() {
  return `
    <div class="screen">
      ${hero("ParkPe CoPilot", "Share the ride. Split the cost.", "Daily office commute and intercity trips with verified drivers.")}
      <form class="screen-panel route-grid" data-ride-form>
        ${field("Leaving from", `<input name="from" required value="Cyber Hub, Gurugram" />`)}
        ${field("Going to", `<input name="to" required value="Noida Sector 62" />`)}
        ${field("When", `<input name="when" type="datetime-local" required />`)}
        <button class="btn-dark" type="submit">Find rides</button>
      </form>
      <div class="stack" data-rides hidden></div>
    </div>`;
}

function transactionsScreen() {
  const rows = [
    ["FASTag recharge", "DL 01 AB 1234 · ICICI", "₹500", "Paid", "status-paid"],
    ["Parking", "Cyber Hub, Gurugram", "₹120", "Active", "status-active"],
    ["Electricity", "BSES Rajdhani", "₹2,140", "Paid", "status-paid"],
    ["Challan", "DL 8C AX 4410", "₹1,000", "Due", "status-due"],
  ]
    .map(
      ([title, meta, amount, status, tone]) => `
      <div class="txn">
        <div><strong>${title}</strong><p>${meta}</p></div>
        <div class="txn-end"><strong>${amount}</strong><span class="status ${tone}">${status}</span></div>
      </div>`,
    )
    .join("");
  return `
    <div class="screen">
      ${hero("Secure payment activity", "Transaction history", "Parking, FASTag, challans, bills and vouchers in one list.")}
      <div class="stat-row">
        <article><span>This month</span><strong>₹3,760</strong></article>
        <article><span>Paid</span><strong>3</strong></article>
        <article><span>Due</span><strong>1</strong></article>
        <article><span>Active</span><strong>1</strong></article>
      </div>
      <label class="search-line">${icon("search")}<input type="search" data-txn-search placeholder="Search transactions" /></label>
      <div class="screen-panel txn-list">${rows}</div>
    </div>`;
}

function connectScreen() {
  return `
    <div class="screen">
      <div class="screen-head">
        <div><h1>Connect Hub</h1><p>Vehicles, QR stickers, chat and calls.</p></div>
        <a class="btn-dark" href="#qr-scan">${icon("add")} Add vehicle</a>
      </div>
      <div class="tabs">
        <button type="button" class="tab is-on" data-tab="vehicles">Vehicles & QR <span>2</span></button>
        <button type="button" class="tab" data-tab="inbox">Chat</button>
        <button type="button" class="tab" data-tab="calls">Calls</button>
      </div>
      <div data-panel="vehicles" class="stack">
        <article class="vehicle-card"><div><strong>DL 01 AB 1234</strong><p>Hyundai Creta · PUC expires in 18 days</p></div><span class="status status-due">PUC</span></article>
        <article class="vehicle-card"><div><strong>HR 26 DK 9081</strong><p>Maruti Suzuki Swift · Insurance expired</p></div><span class="status status-due">Insurance</span></article>
      </div>
      <div data-panel="inbox" class="screen-panel" hidden>
        <article class="txn"><div><strong>Parking marshal</strong><p>Your bay at Cyber Hub is ready.</p></div><span>2m</span></article>
      </div>
      <div data-panel="calls" class="screen-panel empty-copy" hidden>No calls yet.</div>
    </div>`;
}

function parkingScreen() {
  return `
    <div class="screen">
      ${hero("Parking desk", "Customer parking", "Book a bay, see what is live, and review older sessions.")}
      <div class="action-grid">
        <a href="#parking"><span class="tile-icon">${icon("local_parking")}</span><strong>Book parking</strong><p>Find a bay near you.</p></a>
        <a href="#transactions"><span class="tile-icon">${icon("schedule")}</span><strong>Live sessions</strong><p>1 session is active.</p></a>
        <a href="#transactions"><span class="tile-icon">${icon("history")}</span><strong>History</strong><p>Paid and due visits.</p></a>
      </div>
      <form class="screen-panel form-grid">
        <h2>Book a bay</h2>
        ${field("Location", `<input name="location" required placeholder="Cyber Hub, Gurugram" />`)}
        ${field("Vehicle", `<input name="vehicle" required value="DL 01 AB 1234" />`)}
        ${field("From", `<input name="from" type="datetime-local" required />`)}
        <button class="btn-dark" type="submit">Hold this bay</button>
      </form>
    </div>`;
}

function supportScreen() {
  return `
    <div class="screen">
      ${hero("Help centre", "Support", "Open a ticket for parking, payments, or anything else that is stuck.")}
      <form class="screen-panel form-grid">
        ${field("Topic", `<select name="topic"><option>General</option><option>Parking</option><option>Payment</option><option>FASTag</option></select>`)}
        ${field("Subject", `<input name="subject" required placeholder="What do you need help with?" />`)}
        ${field("Details", `<textarea name="details" rows="4" required placeholder="Tell us what happened"></textarea>`)}
        <button class="btn-dark" type="submit">Submit ticket</button>
      </form>
      <section class="screen-panel">
        <h2>Your tickets</h2>
        <article class="txn"><div><strong>FASTag receipt not received</strong><p>Payment · Open</p></div><span class="status status-active">Open</span></article>
      </section>
    </div>`;
}

function settingsScreen() {
  return `
    <div class="screen">
      ${hero("Account settings", "Security", "Password and the alerts this account should receive.")}
      <div class="stat-row">
        <article><span>Password</span><strong>Set</strong></article>
        <article><span>Mobile OTP</span><strong>On</strong></article>
        <article><span>Reminders</span><strong>On</strong></article>
      </div>
      <form class="screen-panel form-grid">
        <h2>Change password</h2>
        ${field("Current password", `<input name="current" type="password" required />`)}
        ${field("New password", `<input name="next" type="password" required minlength="8" />`)}
        ${field("Confirm password", `<input name="confirm" type="password" required minlength="8" />`)}
        <button class="btn-dark" type="submit">Update password</button>
      </form>
    </div>`;
}

function profileScreen() {
  return `
    <div class="screen">
      <header class="profile-hero">
        <span class="avatar avatar-lg">PU</span>
        <div><h1>ParkPe User</h1><p>user@parkpe.in · +91 98000 00010</p></div>
      </header>
      <form class="screen-panel form-grid">
        ${field("Full name", `<input name="name" required value="ParkPe User" />`)}
        ${field("Mobile", `<input name="mobile" required value="9800000010" />`)}
        ${field("Email", `<input name="email" type="email" required value="user@parkpe.in" />`)}
        ${field("City", `<input name="city" value="Gurugram" />`)}
        <button class="btn-dark" type="submit">Save profile</button>
      </form>
    </div>`;
}

function notificationsScreen() {
  return `
    <div class="screen">
      ${hero("Reminders", "Reminders", "Document, FASTag and parking reminders for your vehicles.")}
      <div class="stack">
        <button type="button" class="reminder" data-go="dashboard"><strong>PUC expires in 18 days</strong><p>DL 01 AB 1234</p></button>
        <button type="button" class="reminder" data-go="dashboard"><strong>Insurance has expired</strong><p>HR 26 DK 9081</p></button>
        <button type="button" class="reminder" data-go="fastag"><strong>FASTag balance low</strong><p>HR 26 DK 9081 is below ₹200</p></button>
      </div>
    </div>`;
}

const screens = {
  "bill-payments": billScreen,
  fastag: fastagScreen,
  "pay-challan": challanScreen,
  "qr-scan": qrScreen,
  "parkpe-voucher": voucherScreen,
  "brand-vouchers": brandScreen,
  carpool: carpoolScreen,
  transactions: transactionsScreen,
  connect: connectScreen,
  parking: parkingScreen,
  support: supportScreen,
  "account-settings": settingsScreen,
  profile: profileScreen,
  notifications: notificationsScreen,
};

function toast(message) {
  document.dispatchEvent(new CustomEvent("parkpe-toast", { detail: message }));
}

function onClick(event) {
  const root = event.currentTarget;
  const tab = event.target.closest("[data-tab]");
  if (tab && root.contains(tab)) {
    const group = tab.parentElement;
    group.querySelectorAll("[data-tab]").forEach((button) => button.classList.toggle("is-on", button === tab));
    root.querySelectorAll("[data-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.panel !== tab.dataset.tab;
    });
  }
  const bill = event.target.closest("[data-bill]");
  if (bill && root.contains(bill)) {
    root.querySelector("[data-bill-stage='grid']").hidden = true;
    root.querySelector("[data-bill-side]").hidden = true;
    const ops = root.querySelector("[data-bill-stage='ops']");
    ops.hidden = false;
    ops.innerHTML = billOps(bill.dataset.bill);
  }
  if (event.target.closest("[data-bill-back]")) {
    root.querySelector("[data-bill-stage='ops']").hidden = true;
    root.querySelector("[data-bill-stage='grid']").hidden = false;
    root.querySelector("[data-bill-side]").hidden = false;
  }
  const op = event.target.closest("[data-op]");
  if (op && root.contains(op)) {
    const board = op.closest(".op-board") || root;
    board.querySelectorAll("[data-op]").forEach((item) => item.classList.toggle("is-on", item === op));
    const current = root.querySelector("[data-op-current]");
    if (current) current.textContent = op.dataset.op;
    const mark = root.querySelector("[data-op-mark]");
    if (mark && !mark.querySelector("img")) mark.textContent = op.dataset.op.trim().charAt(0);
    const logo = root.querySelector("[data-op-logo]");
    const img = op.querySelector("img");
    if (logo && img) logo.src = img.src;
  }
  if (event.target.closest("[data-bill-pay]")) {
    root.querySelector("[data-step='pay']")?.classList.add("is-on");
    root.querySelector("[data-step='done']")?.classList.add("is-on");
    toast("Payment stays on this screen until the BBPS API is connected.");
  }
  const filter = event.target.closest("[data-brand-filter]");
  if (filter) {
    filter.parentElement.querySelectorAll("[data-brand-filter]").forEach((button) => {
      button.classList.toggle("is-on", button === filter);
    });
    const category = filter.dataset.brandFilter;
    root.querySelectorAll("[data-brand]").forEach((card) => {
      card.hidden = category !== "All" && card.dataset.category !== category;
    });
  }
  const go = event.target.closest("[data-go]");
  if (go) location.hash = go.dataset.go;
}

function onInput(event) {
  const root = event.currentTarget;
  if (event.target.matches("[data-bill-search]")) {
    const query = event.target.value.trim().toLowerCase();
    root.querySelectorAll("[data-bill]").forEach((tile) => {
      tile.hidden = query && !tile.dataset.bill.toLowerCase().includes(query);
    });
    let any = false;
    root.querySelectorAll("[data-bill-group]").forEach((group) => {
      const visible = [...group.querySelectorAll("[data-bill]")].some((tile) => !tile.hidden);
      group.hidden = !visible;
      if (visible) any = true;
    });
    const empty = root.querySelector("[data-bill-empty]");
    if (empty) empty.hidden = any;
  }
  if (event.target.matches("[data-op-search]")) {
    const query = event.target.value.trim().toLowerCase();
    const board = event.target.closest(".op-board") || root;
    board.querySelectorAll("[data-op]").forEach((row) => {
      row.hidden = query && !row.dataset.op.toLowerCase().includes(query);
    });
  }
  if (event.target.matches("[data-bank-search]")) {
    const query = event.target.value.trim().toLowerCase();
    root.querySelectorAll("[data-bank]").forEach((bank) => {
      bank.hidden = query && !bank.dataset.bank.toLowerCase().includes(query);
    });
  }
  if (event.target.matches("[data-brand-search]")) {
    const query = event.target.value.trim().toLowerCase();
    root.querySelectorAll("[data-brand]").forEach((card) => {
      card.hidden = query && !card.dataset.brand.toLowerCase().includes(query);
    });
  }
  if (event.target.matches("[data-txn-search]")) {
    const query = event.target.value.trim().toLowerCase();
    root.querySelectorAll(".txn").forEach((row) => {
      row.hidden = query && !row.textContent.toLowerCase().includes(query);
    });
  }
}

function onSubmit(event) {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  event.preventDefault();
  const root = event.currentTarget;
  const data = new FormData(form);
  if (form.matches("[data-bill-form]")) {
    const due = form.querySelector("[data-bill-due]");
    const current = form.querySelector("[data-op-current]");
    due.hidden = false;
    due.querySelector("[data-due-account]").textContent = `${current ? current.textContent : "Operator"} · ${data.get("account")}`;
    root.querySelector("[data-step='bill']")?.classList.add("is-on");
    return;
  }
  if (form.matches("[data-challan-form]")) {
    const vehicle = String(data.get("vehicle") || "").toUpperCase();
    const box = root.querySelector("[data-challan-results]");
    box.hidden = false;
    box.innerHTML = `
      <article class="screen-panel">
        <h2>${vehicle || "Vehicle"}</h2>
        <div class="txn"><div><strong>Overspeeding</strong><p>MG Road · 12 Nov 2026</p></div><div class="txn-end"><strong>₹1,000</strong><span class="status status-due">Due</span></div></div>
        <div class="txn"><div><strong>Signal jump</strong><p>Cyber Hub · 02 Oct 2026</p></div><div class="txn-end"><strong>₹500</strong><span class="status status-paid">Paid</span></div></div>
      </article>`;
    return;
  }
  if (form.querySelector("[name='payload']")) {
    const box = root.querySelector("[data-qr-result]");
    box.hidden = false;
    box.innerHTML = `<strong>Parking slip</strong><p>Cyber Hub, bay B12 · token ready to open.</p><a class="btn-dark" href="#parking">Open parking</a>`;
    return;
  }
  if (form.matches("[data-ride-form]")) {
    const box = root.querySelector("[data-rides]");
    box.hidden = false;
    box.innerHTML = `
      <article class="vehicle-card"><div><strong>07:40 · 2 seats</strong><p>${data.get("from")} → ${data.get("to")} · ₹180 share</p></div><span class="status status-paid">Verified</span></article>
      <article class="vehicle-card"><div><strong>08:10 · 1 seat</strong><p>${data.get("from")} → ${data.get("to")} · ₹160 share</p></div><span class="status status-active">Today</span></article>`;
    return;
  }
  toast("Saved on this screen. It will sync when this service API is connected.");
}

let wired = false;

window.ParkpeScreens = {
  mount(root, name) {
    const draw = screens[name];
    root.innerHTML = draw ? draw() : hero("ParkPe", name, "");
    if (!wired) {
      root.addEventListener("click", onClick);
      root.addEventListener("input", onInput);
      root.addEventListener("submit", onSubmit);
      wired = true;
    }
  },
};
})();
