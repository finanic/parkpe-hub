/* ParkPe screens for apps/parkpe/dashboard/index.html.

   Draws parking, FASTag, carpool, QR, and the other in-page views.
   QR submit with site, bay, and vehicle calls apps/parkpe/js/hub.js
   (POST /api/v1/parkpe/sessions/initiate). Other forms stay on this page.
   Must not load apps/payswap/js/session.js.
*/
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
const rtoStates = [
  ["", "All India — optional"],
  ["AN", "Andaman & Nicobar Islands"],
  ["AP", "Andhra Pradesh"],
  ["AR", "Arunachal Pradesh"],
  ["AS", "Assam"],
  ["BR", "Bihar"],
  ["CH", "Chandigarh"],
  ["CG", "Chhattisgarh"],
  ["DN", "Dadra & Nagar Haveli and Daman & Diu"],
  ["DL", "Delhi"],
  ["GA", "Goa"],
  ["GJ", "Gujarat"],
  ["HR", "Haryana"],
  ["HP", "Himachal Pradesh"],
  ["JK", "Jammu & Kashmir"],
  ["JH", "Jharkhand"],
  ["KA", "Karnataka"],
  ["KL", "Kerala"],
  ["LA", "Ladakh"],
  ["LD", "Lakshadweep"],
  ["MP", "Madhya Pradesh"],
  ["MH", "Maharashtra"],
  ["MN", "Manipur"],
  ["ML", "Meghalaya"],
  ["MZ", "Mizoram"],
  ["NL", "Nagaland"],
  ["OD", "Odisha"],
  ["PY", "Puducherry"],
  ["PB", "Punjab"],
  ["RJ", "Rajasthan"],
  ["SK", "Sikkim"],
  ["TN", "Tamil Nadu"],
  ["TS", "Telangana"],
  ["TR", "Tripura"],
  ["UP", "Uttar Pradesh"],
  ["UK", "Uttarakhand"],
  ["WB", "West Bengal"],
];

const brands = [
  ["swiggy", "Swiggy", "food", 10, "Food delivery in minutes", "100,250,500,1000,2000", "#ff7417"],
  ["zomato", "Zomato", "food", 8, "Discover restaurants & order food", "100,250,500,1000,2000", "#f32d45"],
  ["dominos", "Domino's", "food", 12, "Pizza delivery & more", "250,500,1000", "#087ba4"],
  ["mcdonalds", "McDonald's", "food", 10, "I'm lovin' it", "250,500,1000", "#e91b13"],
  ["kfc", "KFC", "food", 10, "It's finger lickin' good", "250,500,1000", "#f70846"],
  ["starbucks", "Starbucks", "food", 8, "Coffee & beverages", "250,500,1000,2000", "#00834f"],
  ["amazon", "Amazon", "shopping", 5, "Shop millions of products", "100,250,500,1000,2000,5000", "#ff9900"],
  ["flipkart", "Flipkart", "shopping", 6, "India's marketplace", "100,250,500,1000,2000,5000", "#2f6fec"],
  ["myntra", "Myntra", "shopping", 10, "Fashion & lifestyle", "250,500,1000,2000", "#ff3f6c"],
  ["ajio", "AJIO", "shopping", 12, "Curated fashion brands", "250,500,1000,2000", "#171717"],
  ["nykaa", "Nykaa", "shopping", 8, "Beauty & wellness", "250,500,1000,2000", "#fc2779"],
  ["tatacliQ", "Tata CLiQ", "shopping", 7, "Premium shopping experience", "250,500,1000,2000", "#5145ff"],
  ["uber", "Uber", "travel", 8, "Ride at your fingertips", "100,250,500,1000", "#000000"],
  ["ola", "Ola", "travel", 10, "India's ride platform", "100,250,500,1000", "#27c66f"],
  ["makemytrip", "MakeMyTrip", "travel", 6, "Flights, hotels & holidays", "500,1000,2000,5000", "#f31335"],
  ["netflix", "Netflix", "entertainment", 5, "Stream unlimited content", "199,499,649", "#151515"],
  ["spotify", "Spotify", "entertainment", 8, "Music for everyone", "119,179,299", "#1db954"],
  ["bookmyshow", "BookMyShow", "entertainment", 10, "Movies, events & more", "250,500,1000", "#e60000"],
  ["bigbasket", "BigBasket", "grocery", 8, "Fresh groceries delivered", "250,500,1000,2000", "#7fc719"],
  ["blinkit", "Blinkit", "grocery", 6, "10-minute grocery delivery", "100,250,500,1000", "#ffc514"],
];

const brandGroups = [
  ["food", "Food & Dining", "restaurant"],
  ["shopping", "Shopping", "shopping_bag"],
  ["travel", "Travel & Rides", "flight"],
  ["entertainment", "Entertainment", "movie"],
  ["grocery", "Grocery", "shopping_cart"],
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

function brandInitial(name) {
  const trimmed = name.trim();
  if (trimmed.startsWith("Mc")) return "M";
  return trimmed.charAt(0).toUpperCase();
}

function applyBrandFilters(root) {
  const query = (root.querySelector("[data-brand-search]")?.value || "").trim().toLowerCase();
  const active = root.querySelector("[data-brand-filter].is-on");
  const category = active ? active.dataset.brandFilter : "all";
  root.querySelectorAll("[data-brand]").forEach((card) => {
    const nameOk = !query || card.dataset.brand.toLowerCase().includes(query);
    const catOk = category === "all" || card.dataset.category === category;
    card.hidden = !(nameOk && catOk);
  });
  root.querySelectorAll("[data-brand-group]").forEach((group) => {
    group.hidden = ![...group.querySelectorAll("[data-brand]")].some((card) => !card.hidden);
  });
  const empty = root.querySelector("[data-brand-empty]");
  if (empty) empty.hidden = [...root.querySelectorAll("[data-brand]")].some((card) => !card.hidden);
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
  const features = ["24/7 Available", "Instant Recharge", "No Cash Needed", "Secure Payment", "Pan India Toll", "Quick Deduction"]
    .map(
      (label) => `<span class="svc-feature"><span><i></i>${label}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4 12 14.01l-3-3"/></svg></span>`,
    )
    .join("");
  return `
    <section class="svc">
      <div class="svc-lime">
        <p class="svc-kicker">Retailer Service</p>
        <h1>FASTag</h1>
        <p>Recharge FASTag, verify vehicle details and track customer recharge status quickly.</p>
      </div>
      <div class="svc-split">
        <form class="svc-card" data-fastag-form>
          <p class="svc-kicker svc-kicker-dark">Retailer Service</p>
          <h2>FASTag Recharge</h2>
          <label class="svc-label">Biller
            <input class="svc-input" type="search" data-op-search placeholder="Search your FASTag bank" />
          </label>
          <p class="svc-selected">Selected issuer · <strong data-op-current>ICICI Bank</strong></p>
          <div class="op-list svc-issuers" role="listbox" aria-label="FASTag issuers">${rows}</div>
          <p class="svc-count">${fastagIssuers.length} issuers</p>
          <label class="svc-label">Vehicle Number
            <input class="svc-input svc-upper" name="vehicle" required placeholder="Enter vehicle number" autocomplete="off" />
          </label>
          <button class="svc-submit" type="submit">Submit</button>
        </form>
        <aside class="svc-aside">
          <h2>FASTag Service</h2>
          <p>FASTag is an electronic toll collection system that enables automatic toll payment from a linked wallet or bank account. It helps vehicles pass through toll plazas faster without cash handling.</p>
          <div class="svc-features">${features}</div>
          <div class="svc-note">
            <p>Important</p>
            <span>Make sure the vehicle number is correct before recharge. Wrong vehicle details may recharge another FASTag account.</span>
          </div>
        </aside>
      </div>
    </section>`;
}

function challanScreen() {
  const states = rtoStates
    .map(([code, name]) => `<option value="${esc(code)}">${esc(code ? `${code} — ${name}` : name)}</option>`)
    .join("");
  return `
    <section class="svc svc-challan">
      <header class="svc-challan-hero">
        <div>
          <p class="svc-kicker svc-kicker-olive">Traffic Services</p>
          <h1>Traffic Challans</h1>
          <p>Check and pay your pending traffic challans instantly.<br />Fast, secure and hassle-free.</p>
          <div class="svc-promises">
            <div><span class="mi">verified_user</span><div><strong>100% Secure</strong><small>Your data is protected</small></div></div>
            <div><span class="mi">bolt</span><div><strong>Instant Results</strong><small>Get challan details instantly</small></div></div>
            <div><span class="mi">payments</span><div><strong>Multiple Payments</strong><small>UPI, Cards, Net Banking & more</small></div></div>
          </div>
        </div>
        <img src="../assets/images/dashboard/pay-challan-hd.png" alt="" />
      </header>
      <form class="svc-card svc-challan-form" data-challan-form>
        <div class="svc-stephead">
          <span>1</span>
          <div><h2>Enter Vehicle Details</h2><p>Enter your vehicle number to check pending challans</p></div>
        </div>
        <div class="svc-challan-grid">
          <label>Vehicle Number
            <span class="svc-icon-field"><span class="mi">directions_car</span><input name="vehicle" required placeholder="e.g. KA01AB1234" autocomplete="off" /></span>
            <small>Enter valid vehicle registration number</small>
          </label>
          <label>State / RTO (Optional)
            <span class="svc-icon-field"><span class="mi">location_on</span><select name="state">${states}</select><span class="mi svc-chev">keyboard_arrow_down</span></span>
            <small>Select state or RTO to narrow down results</small>
          </label>
          <aside class="svc-safe">
            <span class="mi">verified_user</span>
            <div><strong>Your data is safe</strong><p>We never share your personal information with anyone.</p></div>
          </aside>
        </div>
        <div class="svc-challan-actions">
          <button type="submit">Search Challans <span class="mi">arrow_forward</span></button>
          <span><span class="mi">lock</span> Secure <i>|</i> Private <i>|</i> Trusted by Millions</span>
        </div>
        <div data-challan-results hidden>
          <header class="ditto-challan-head">
            <p class="svc-kicker svc-kicker-olive"><span class="mi">arrow_back</span> Traffic services</p>
            <h2>Traffic Challans</h2>
            <p>Check and pay your pending traffic challans instantly. Fast, secure and hassle-free.</p>
            <div class="svc-pills"><span><span class="mi">directions_car</span> <b data-challan-vehicle>DL01AB1234</b></span><span><span class="mi">verified_user</span> Secure lookup</span></div>
          </header>
          <div class="ditto-challan-stats">
            <article><span class="mi">receipt_long</span><div><small>Records</small><strong>2</strong></div><em>Total</em></article>
            <article class="is-due"><span class="mi">error</span><div><small>Outstanding</small><strong>1</strong><p>₹1,000</p></div></article>
            <article class="is-paid"><span class="mi">check_circle</span><div><small>Settled</small><strong>1</strong><p>₹500</p></div></article>
          </div>
          <div class="ditto-selectbar">
            <label><input type="checkbox" data-challan-all /> Select all</label>
            <button type="button" data-challan-clear>Clear</button>
            <span data-challan-count>0 selected · ₹0</span>
          </div>
          <label class="ditto-challan-row">
            <input type="checkbox" data-challan-pick data-rupee="1000" />
            <div>
              <div class="ditto-challan-meta"><strong>DL2026/11012</strong><span class="svc-pill">Due</span><span class="svc-pill">DL</span></div>
              <p>Overspeeding</p>
              <small><span class="mi">calendar_month</span> 12 Nov 2026 · <span class="mi">location_on</span> MG Road · <span class="mi">directions_car</span> <b data-challan-vehicle>DL01AB1234</b></small>
            </div>
            <dl><div><dt>Owner</dt><dd>ParkPe User</dd></div><div><dt>Authority</dt><dd>Delhi Traffic Police</dd></div></dl>
            <div class="ditto-amt"><small>Amount</small><strong>₹1,000</strong><span>Base ₹800</span><span>+ penalty ₹200</span></div>
          </label>
          <article class="ditto-challan-row is-settled">
            <div>
              <div class="ditto-challan-meta"><strong>DL2026/09044</strong><span class="svc-pill">Paid</span></div>
              <p>Signal jump</p>
              <small><span class="mi">calendar_month</span> 02 Oct 2026 · <span class="mi">location_on</span> Cyber Hub</small>
            </div>
            <dl><div><dt>Authority</dt><dd>Delhi Traffic Police</dd></div></dl>
            <div class="ditto-amt"><small>Amount</small><strong>₹500</strong></div>
          </article>
          <article class="svc-card ditto-pay">
            <span class="mi">account_balance</span>
            <div><h3>UPI or card</h3><p>Pay securely through ParkPe. Each challan is confirmed with the traffic authority one at a time.</p><b data-challan-count>0 selected · ₹0</b></div>
            <button type="button" data-challan-pay>Pay selected</button>
          </article>
        </div>
      </form>
      <section class="svc-card">
        <h2>How it works?</h2>
        <div class="svc-how">
          <div><span class="mi">find_in_page</span><div><small>01</small><strong>Enter Details</strong><p>Provide your vehicle number and state</p></div></div>
          <div><span class="mi">fact_check</span><div><small>02</small><strong>View Challans</strong><p>We will show all pending challans</p></div></div>
          <div><span class="mi">credit_card</span><div><small>03</small><strong>Pay Securely</strong><p>Pay using UPI, cards or wallet in seconds</p></div></div>
        </div>
      </section>
      <section class="svc-trust" aria-label="Trust highlights">
        <div><span class="mi">shield</span><div><strong>Bank Level Security</strong><small>256-bit encryption</small></div></div>
        <div><span class="mi">bolt</span><div><strong>Instant Payment</strong><small>UPI, cards, wallet</small></div></div>
        <div><span class="mi">workspace_premium</span><div><strong>Trusted Platform</strong><small>Used by 3Cr+ users</small></div></div>
        <div><span class="mi">support_agent</span><div><strong>24x7 Support</strong><small>We are here to help</small></div></div>
      </section>
    </section>`;
}

function qrScreen() {
  return `
    <section class="svc svc-narrow">
      <div class="svc-card">
        <h1>Scan ParkPe QR</h1>
        <p class="svc-muted">Paste a Connect link, parking slip token, or CoPilot trip code.</p>
      </div>
      <form class="svc-qr" data-qr-form>
        <textarea name="payload" rows="4" required placeholder="Paste QR content or URL…"></textarea>
        <div class="svc-qr-extra">
          <label>Site<input name="site_code" placeholder="HUB1" autocomplete="off" /></label>
          <label>Bay<input name="bay" placeholder="A1" autocomplete="off" /></label>
          <label>Vehicle<input name="vehicle" placeholder="DL01AB1234" autocomplete="off" /></label>
        </div>
        <button class="svc-submit" type="submit">Resolve QR</button>
      </form>
      <div class="svc-qr-result" data-qr-result hidden></div>
    </section>`;
}

function voucherScreen() {
  return `
    <section class="svc svc-voucher">
      <div data-voucher-view="home">
        <header class="svc-voucher-hero">
          <div>
            <h1>ParkPe &amp;<br />Vouchers</h1>
            <p>Secure, instant gifting with trusted ParkPe vouchers for every occasion.</p>
          </div>
          <img src="../assets/images/dashboard/card_voucher12.png" alt="ParkPe gift voucher" />
          <div class="svc-voucher-float">
            <span class="mi">verified</span>
            <div><strong>Instant voucher creation</strong><small>Separate voucher for every successful payment.</small></div>
          </div>
        </header>
        <section class="svc-card svc-voucher-list">
          <div class="svc-voucher-bar">
            <div class="svc-title-row">
              <span class="mi">confirmation_number</span>
              <div><h2>ParkPe voucher list</h2><p>Showing 1-2 of 2 vouchers</p></div>
            </div>
            <label class="svc-search"><input type="search" data-voucher-search placeholder="Search voucher, reference or amount..." /><span class="mi">search</span></label>
            <div class="svc-voucher-actions">
              <button type="button" data-voucher="buy"><span class="mi">add_card</span>Buy Voucher</button>
              <button type="button" data-voucher="link"><span class="mi">link</span>Link a Voucher</button>
              <button type="button" data-voucher="transactions"><span class="mi">receipt_long</span>Transactions</button>
              <button type="button" data-voucher="display"><span class="mi">desktop_windows</span>Display</button>
              <button type="button" data-voucher="manage"><span class="mi">dashboard_customize</span>Manage cards</button>
            </div>
          </div>
          <div class="svc-stats">
            <article><div><small>Active</small><strong>1</strong></div><span class="mi">confirmation_number</span></article>
            <article><div><small>Balance</small><strong>Rs 1,250</strong></div><span class="mi">account_balance_wallet</span></article>
            <article><div><small>Used</small><strong>1</strong></div><span class="mi">receipt_long</span></article>
            <article><div><small>Linked</small><strong>2</strong></div><span class="mi">link</span></article>
          </div>
          <div class="svc-table-head"><span>Category</span><span>Voucher code</span><span>Amount</span><span>Status</span><span>Action</span></div>
          <div class="svc-table-row" data-voucher-row>
            <div><span class="mi">confirmation_number</span><div><strong>ParkPe</strong><small>Issued 12 Aug 2026</small></div></div>
            <div><strong>PP-20481</strong><small>REF-20481</small></div>
            <div><strong>Rs 1250.00</strong><small>12 Aug 2026</small></div>
            <span class="svc-pill">Active</span>
            <button type="button" data-voucher="detail" data-code="PP-20481" data-ref="REF-20481" data-amount="1250.00" data-issued="12 Aug 2026" data-status="Active">Open</button>
          </div>
          <div class="svc-table-row" data-voucher-row>
            <div><span class="mi">confirmation_number</span><div><strong>ParkPe</strong><small>Issued 02 Jan 2026</small></div></div>
            <div><strong>PP-19802</strong><small>REF-19802</small></div>
            <div><strong>Rs 0.00</strong><small>02 Jan 2026</small></div>
            <span class="svc-pill">Used</span>
            <button type="button" data-voucher="detail" data-code="PP-19802" data-ref="REF-19802" data-amount="0.00" data-issued="02 Jan 2026" data-status="Used">Open</button>
          </div>
        </section>
      </div>
      <div data-voucher-view="buy" hidden>
        <button class="svc-back" type="button" data-voucher="home"><span class="mi">arrow_back</span>Back to vouchers</button>
        <div class="svc-two">
          <form class="svc-card">
            <div class="svc-title-row"><span class="mi">add_card</span><div><h2>Buy ParkPe voucher</h2><p>Create a voucher with secure ParkPe checkout.</p></div></div>
            <label class="svc-label">Amount (INR)
              <small>Minimum Rs 100 · Maximum Rs 10,000</small>
              <span class="svc-rupee"><b>Rs</b><input data-amount-input name="amount" type="number" min="100" max="10000" value="1000" /></span>
            </label>
            <div class="svc-chips">
              ${[100, 500, 1000, 2000, 5000, 10000].map((amount) => `<button type="button" data-amount="${amount}" class="${amount === 1000 ? "is-on" : ""}">Rs ${amount}</button>`).join("")}
            </div>
            <button class="svc-submit" type="submit"><span class="mi">lock</span> Pay securely with ParkPe <span class="mi">arrow_forward</span></button>
          </form>
          <aside class="svc-rules">
            <p class="svc-kicker">Voucher rules</p>
            <h3>Safe, instant, separate</h3>
            <div><strong>One payment, one voucher</strong><p>Each successful payment creates its own voucher.</p></div>
            <div><strong>Rs 100 to Rs 10,000</strong><p>Stay inside the voucher amount range.</p></div>
            <div><strong>Use it on ParkPe</strong><p>Parking, bills and other ParkPe services.</p></div>
          </aside>
        </div>
      </div>
      <div data-voucher-view="link" hidden>
        <button class="svc-back" type="button" data-voucher="home"><span class="mi">arrow_back</span>Back to vouchers</button>
        <div class="svc-two">
          <form class="svc-card">
            <div class="svc-title-row"><span class="mi">link</span><div><h2>Link a voucher</h2><p>Add an existing ParkPe voucher securely.</p></div></div>
            <div class="svc-pair">
              <label>Voucher code<input name="code" placeholder="Enter voucher code" autocomplete="off" /></label>
              <label>PIN<span class="svc-pin"><input name="pin" type="password" data-pin-input placeholder="Enter PIN" autocomplete="one-time-code" /><button type="button" data-pin aria-label="Toggle PIN visibility"><span class="mi">visibility</span></button></span></label>
            </div>
            <button class="svc-submit svc-submit-soft" type="submit"><span class="mi">link</span> Link to my account <span class="mi">arrow_forward</span></button>
          </form>
          <aside class="svc-rules">
            <p class="svc-kicker">Secure linking</p>
            <h3>Credentials stay protected</h3>
            <div><strong>Code and PIN together</strong><p>Both are required before a voucher is linked.</p></div>
            <div><strong>One account</strong><p>A voucher links to the signed-in ParkPe account.</p></div>
          </aside>
        </div>
      </div>
      <div data-voucher-view="balance" hidden>
        <button class="svc-back" type="button" data-voucher="home"><span class="mi">arrow_back</span>Back to vouchers</button>
        <section class="svc-balance">
          <div>
            <div class="svc-title-row"><span class="mi">account_balance_wallet</span><div><p class="svc-kicker">ParkPe voucher</p><h2>Check voucher balance</h2><p>Verify your purchased 16-digit voucher securely.</p></div></div>
            <form class="svc-balance-form">
              <label class="svc-icon-field"><span class="mi">pin</span><input name="code" inputmode="numeric" maxlength="19" placeholder="Enter your Voucher Code" /></label>
              <button type="submit">Check Balance <span class="mi">arrow_forward</span></button>
            </form>
          </div>
          <aside>
            <p class="svc-kicker">Available balance</p>
            <strong data-balance-value>Rs 1250.00</strong>
            <p data-balance-note>PP-20481 is active on this account.</p>
          </aside>
        </section>
      </div>
      <div data-voucher-view="transactions" hidden>
        <button class="svc-back" type="button" data-voucher="home"><span class="mi">arrow_back</span>Back to vouchers</button>
        <section class="svc-card ditto-panel">
          <header class="ditto-panel-head">
            <div class="svc-title-row"><span class="mi">receipt_long</span><div><h2>ParkPe Voucher Transactions</h2><p>2 purchased voucher records</p></div></div>
            <button type="button" class="svc-submit" data-voucher="buy">Buy ParkPe voucher</button>
          </header>
          <div class="ditto-txn-head"><span>When</span><span>Voucher code</span><span>Type</span><span>Amount</span><span>Reference</span><span>Status</span></div>
          <div class="ditto-txn-row"><span>12 Aug 2026</span><span>PP-20481</span><span>TOPUP_PG</span><span class="ditto-plus">+ Rs 1250.00</span><span>REF-20481</span><span class="svc-pill">Completed</span></div>
          <div class="ditto-txn-row"><span>02 Jan 2026</span><span>PP-19802</span><span>TOPUP_PG</span><span class="ditto-plus">+ Rs 500.00</span><span>REF-19802</span><span class="svc-pill">Completed</span></div>
        </section>
      </div>
      <div data-voucher-view="display" hidden>
        <button class="svc-back" type="button" data-voucher="home"><span class="mi">arrow_back</span>Back to vouchers</button>
        <section class="svc-card">
          <div class="svc-title-row"><span class="mi">desktop_windows</span><div><h2>Real display</h2><p>A presentation view for purchased ParkPe vouchers.</p></div></div>
          <div class="ditto-cards">
            <article class="ditto-vcard ditto-vcard-a"><div><header><strong>ParkPe</strong><span class="mi">confirmation_number</span></header><p>Rs 1250.00</p><small>Available Balance</small></div><footer><span>Voucher Code<strong>PP-20481</strong></span><span>Issued On<strong>12 Aug 2026</strong></span></footer></article>
            <article class="ditto-vcard ditto-vcard-b"><div><header><strong>ParkPe</strong><span class="mi">confirmation_number</span></header><p>Rs 0.00</p><small>Available Balance</small></div><footer><span>Voucher Code<strong>PP-19802</strong></span><span>Issued On<strong>02 Jan 2026</strong></span></footer></article>
          </div>
        </section>
      </div>
      <div data-voucher-view="manage" hidden>
        <button class="svc-back" type="button" data-voucher="home"><span class="mi">arrow_back</span>Back to vouchers</button>
        <section class="svc-card">
          <div class="svc-title-row"><span class="mi">dashboard_customize</span><div><h2>Lock &amp; Unlock Cards</h2><p>View purchased vouchers and open details for support actions.</p></div></div>
          <div class="ditto-manage">
            <article><b>1</b><div><strong>REF-20481</strong><span>Voucher PP-20481 · Active · 12 Aug 2026</span></div><button type="button" data-voucher="detail" data-code="PP-20481" data-ref="REF-20481" data-amount="1250.00" data-issued="12 Aug 2026" data-status="Active">View details</button></article>
            <article><b>2</b><div><strong>REF-19802</strong><span>Voucher PP-19802 · Used · 02 Jan 2026</span></div><button type="button" data-voucher="detail" data-code="PP-19802" data-ref="REF-19802" data-amount="0.00" data-issued="02 Jan 2026" data-status="Used">View details</button></article>
          </div>
        </section>
      </div>
      <div data-voucher-view="detail" hidden>
        <header class="svc-card ditto-detail-head">
          <button class="svc-round" type="button" data-voucher="home" aria-label="Back to vouchers"><span class="mi">arrow_back</span></button>
          <span class="svc-bag"><span class="mi">confirmation_number</span></span>
          <div><h1>Voucher detail</h1><p>Balance, PIN for bill pay, and ledger activity</p></div>
          <button type="button" class="svc-outline" data-voucher="home"><span class="mi">list</span>All vouchers</button>
        </header>
        <section class="svc-card ditto-detail">
          <div>
            <p class="svc-kicker">Voucher code</p>
            <strong data-v-code>PP-20481</strong>
            <p class="svc-kicker">Reference</p>
            <span data-v-ref>REF-20481</span>
            <p data-v-issued>Created 12 Aug 2026</p>
            <span class="svc-pill" data-v-status>Active</span>
          </div>
          <aside>
            <p class="svc-kicker">Balance</p>
            <strong data-v-balance>₹1250.00</strong>
            <p data-v-original>Original ₹1250.00</p>
          </aside>
        </section>
        <section class="svc-card">
          <h2>Ledger</h2>
          <div class="ditto-txn-row"><span data-v-issued-row>12 Aug 2026</span><span>Purchase</span><span class="ditto-plus" data-v-ledger>+ Rs 1250.00</span><span class="svc-pill">Completed</span></div>
        </section>
      </div>
    </section>`;
}

function brandScreen() {
  const groups = brandGroups
    .map(([key, label, glyph]) => {
      const cards = brands
        .filter((brand) => brand[2] === key)
        .map(
          ([id, name, category, off, tagline, amounts, color]) => `
          <article class="svc-brand" data-brand="${esc(name)}" data-category="${category}">
            <span class="svc-off">${off}% OFF</span>
            <span class="svc-avatar" style="background:${color}">${brandInitial(name)}</span>
            <h3>${esc(name)}</h3>
            <p>${esc(tagline)}</p>
            <button type="button" data-brand-buy="${esc(name)}" data-off="${off}" data-color="${color}" data-amounts="${amounts}" data-initial="${brandInitial(name)}"><span class="mi">shopping_cart</span>Buy</button>
          </article>`,
        )
        .join("");
      return `
        <section class="svc-card svc-brand-group" data-brand-group="${key}">
          <header><div><span class="mi">${glyph}</span><h2>${label}</h2></div><span>${cards ? brands.filter((brand) => brand[2] === key).length : 0} BRANDS</span></header>
          <div class="svc-brand-grid">${cards}</div>
        </section>`;
    })
    .join("");
  const chips = [
    ["all", "All Brands", "grid_view"],
    ["food", "Food & Dining", "restaurant"],
    ["shopping", "Shopping", "shopping_bag"],
    ["travel", "Travel & Rides", "flight"],
    ["entertainment", "Entertainment", "movie"],
    ["grocery", "Grocery", "shopping_cart"],
  ]
    .map(
      ([key, label, glyph], index) =>
        `<button type="button" class="svc-chip ${index === 0 ? "is-on" : ""}" data-brand-filter="${key}"><span class="mi">${glyph}</span>${label}</button>`,
    )
    .join("");
  const savers = [...brands]
    .sort((a, b) => b[3] - a[3])
    .slice(0, 5)
    .map(
      ([, name, , off, tagline, amounts, color]) =>
        `<button type="button" data-brand-buy="${esc(name)}" data-off="${off}" data-color="${color}" data-amounts="${amounts}" data-initial="${brandInitial(name)}"><span class="svc-avatar" style="background:${color}">${brandInitial(name)}</span><span><strong>${esc(name)}</strong><small>${esc(tagline)}</small></span><b>${off}% OFF</b></button>`,
    )
    .join("");
  return `
    <section class="svc">
      <div class="svc-card svc-brand-head">
        <div class="svc-brand-title">
          <a class="svc-round" href="#dashboard" aria-label="Back to dashboard"><span class="mi">arrow_back</span></a>
          <span class="svc-bag"><span class="mi">shopping_bag</span></span>
          <div><h1>Buy vouchers</h1><p>${brands.length} brands · Save up to 12%</p></div>
        </div>
        <a class="svc-outline" href="#parkpe-voucher"><span class="mi">receipt_long</span>My voucher activity</a>
        <label class="svc-search svc-search-lg"><span class="mi">search</span><input type="search" data-brand-search placeholder="Search by brand name..." /></label>
        <div class="svc-chips">${chips}</div>
      </div>
      <div class="svc-brand-layout">
        <div class="svc-brand-main">
          ${groups}
          <section class="svc-empty" data-brand-empty hidden>
            <span class="mi">search_off</span>
            <h2>No brands found</h2>
            <p>Try another search or category.</p>
          </section>
        </div>
        <aside class="svc-brand-side">
          <section class="svc-card">
            <div class="svc-side-head"><h2>How it works</h2><span>?</span></div>
            <div class="svc-steps">
              <div><b>1</b><div><strong>Choose a brand</strong><p>Browse top brands across food, shopping, travel and more.</p></div></div>
              <div><b>2</b><div><strong>Pick denomination</strong><p>Select the voucher amount you want from Rs 100 to Rs 5000.</p></div></div>
              <div><b>3</b><div><strong>Pay securely</strong><p>Complete payment via UPI, Card or Netbanking in seconds.</p></div></div>
              <div><b>4</b><div><strong>Use your voucher</strong><p>Receive the code instantly and redeem at the brand app or store.</p></div></div>
            </div>
          </section>
          <section class="svc-why">
            <div class="svc-title-row"><span class="mi">savings</span><h2>Why vouchers?</h2></div>
            <ul>
              <li>Instant savings, no extra coupons</li>
              <li>Digital delivery after payment</li>
              <li>Redeem online or in-store</li>
              <li>Secure checkout via ParkPe</li>
            </ul>
          </section>
          <section class="svc-card">
            <h2>Top savers</h2>
            <p class="svc-muted">Highest discounts right now</p>
            <div class="svc-savers">${savers}</div>
          </section>
        </aside>
      </div>
      <div class="svc-modal" data-brand-sheet hidden>
        <section class="svc-modal-card">
          <div class="svc-modal-head">
            <span class="svc-avatar" data-brand-mark>S</span>
            <div><h2 data-brand-name>Brand voucher</h2><p data-brand-off>Save on this purchase</p></div>
            <button type="button" data-brand-close aria-label="Close"><span class="mi">close</span></button>
          </div>
          <p class="svc-label">Choose denomination</p>
          <div class="svc-denoms" data-denoms></div>
          <button class="svc-submit" type="button" data-brand-pay>Pay securely</button>
        </section>
      </div>
    </section>`;
}

function carpoolScreen() {
  return `
    <section class="svc">
      <div data-ride-view="home">
      <div class="svc-ride">
        <div class="svc-ride-top">
          <div>
            <p class="svc-kicker">ParkPe CoPilot</p>
            <h1>Share the ride. Split the cost.</h1>
            <p>Daily office commute and intercity trips with verified drivers — cost-sharing only, not a taxi service.</p>
          </div>
          <span class="svc-ride-mark"><span class="mi">hail</span></span>
        </div>
        <form class="svc-ride-form" data-ride-form>
          <label>Leaving from<input name="from" required value="Cyber Hub, Gurugram" /></label>
          <span class="svc-swap" aria-hidden="true"><span class="mi">swap_vert</span></span>
          <label>Going to<input name="to" required value="Noida Sector 62" /></label>
          <p class="svc-hint">Pick a city or locality on both sides, then search seats on that route.</p>
        <div>
          <button type="submit"><span class="mi">search</span>Find a ride</button>
          <button type="button" class="svc-ghost" data-ride="driver">Offer a ride</button>
          <button type="button" class="svc-ghost" data-ride="trips">My trips</button>
          <button type="button" class="svc-ghost" data-ride="passenger">Passenger setup</button>
        </div>
        </form>
        <div class="svc-pills"><span>Cost-share compliant</span><span>VRN-bound driver vouchers</span><span>DL + vehicle verified</span></div>
      </div>
      <div class="svc-empty" data-rides>
        <span class="mi">directions_car</span>
        <p>No trips yet</p>
        <small>Search for a seat or publish your empty seats on a route you drive often.</small>
      </div>
      <form class="svc-card" data-offer-form hidden>
        <h2>Offer a ride</h2>
        <p class="svc-muted">Publish empty seats on a route you already drive.</p>
        <div class="svc-pair">
          <label>From<input name="from" required value="Cyber Hub, Gurugram" /></label>
          <label>To<input name="to" required value="Noida Sector 62" /></label>
        </div>
        <label class="svc-label">Seats<input class="svc-input" name="seats" type="number" min="1" value="2" /></label>
        <button class="svc-submit" type="submit">Publish trip</button>
      </form>
      </div>
      <div data-ride-view="search" hidden>
        <button class="svc-back" type="button" data-ride="home"><span class="mi">arrow_back</span>CoPilot home</button>
        <p class="svc-kicker">Available rides</p>
        <h1>Pick a trip and book a seat</h1>
        <p class="svc-muted">You pay your share of fuel and tolls. <span data-ride-route>Cyber Hub, Gurugram → Noida Sector 62</span></p>
        <form class="svc-card ditto-filters">
          <label>Date<input type="date" value="2026-11-25" /></label>
          <label>From time<input type="time" value="07:00" /></label>
          <label>Until time<input type="time" value="10:00" /></label>
          <label>Sort<select><option>Departure time</option><option>Lowest price</option><option>Driver rating</option><option>Most trips</option></select></label>
          <label class="ditto-check"><input type="checkbox" checked /> Instant booking only</label>
          <label class="ditto-check"><input type="checkbox" /> Women only</label>
          <label class="ditto-check"><input type="checkbox" checked /> Verified drivers only</label>
        </form>
        <div class="ditto-trips">
          <button type="button" data-ride="trip" data-when="07:40" data-price="180" data-driver="A. Sharma" data-seats="2">
            <span><b>07:40</b><i></i></span>
            <span><strong data-ride-from>Cyber Hub, Gurugram</strong><strong data-ride-to>Noida Sector 62</strong><small>A. Sharma · Verified · ★ 4.8 · 126 trips · 25 Nov 2026</small></span>
            <span><b>₹180</b><small>per seat · 2 free</small></span>
          </button>
          <button type="button" data-ride="trip" data-when="08:10" data-price="160" data-driver="R. Iyer" data-seats="1">
            <span><b>08:10</b><i></i></span>
            <span><strong data-ride-from>Cyber Hub, Gurugram</strong><strong data-ride-to>Noida Sector 62</strong><small>R. Iyer · Instant · ★ 4.6 · 54 trips · 25 Nov 2026</small></span>
            <span><b>₹160</b><small>per seat · 1 free</small></span>
          </button>
        </div>
      </div>
      <div data-ride-view="trip" hidden>
        <button class="svc-back" type="button" data-ride="search"><span class="mi">arrow_back</span>Available rides</button>
        <section class="svc-card ditto-trip">
          <div><span class="svc-pill">Open</span><span class="svc-pill">Instant</span><p data-trip-when>25 Nov 2026 · 07:40</p></div>
          <strong data-trip-price>₹180</strong>
          <ol>
            <li><small>Pickup</small><b data-ride-from>Cyber Hub, Gurugram</b></li>
            <li><small>Drop-off</small><b data-ride-to>Noida Sector 62</b></li>
          </ol>
          <p>Driver <b data-trip-driver>A. Sharma</b> · <span data-trip-seats>2</span> seats free · cost-share only.</p>
          <button type="button" class="svc-submit" data-ride-book>Request seat</button>
        </section>
      </div>
      <div data-ride-view="trips" hidden>
        <button class="svc-back" type="button" data-ride="home"><span class="mi">arrow_back</span>CoPilot</button>
        <h1>My trips</h1>
        <section class="svc-card"><h2>Upcoming as passenger</h2><article class="ditto-history"><div><strong>Cyber Hub → Noida Sector 62</strong><p>25 Nov 2026 · 07:40 · Requested</p></div><b>₹180</b></article></section>
        <section class="svc-card"><h2>Your published trips</h2><article class="ditto-history"><div><strong>DLF Phase 2 → Cyber Hub</strong><p>Weekdays · 2 seats · Open</p></div><b>₹90</b></article></section>
      </div>
      <div data-ride-view="driver" hidden>
        <button class="svc-back" type="button" data-ride="home"><span class="mi">arrow_back</span>CoPilot</button>
        <p class="svc-kicker">Driver</p>
        <h1>Offer a ride</h1>
        <p class="svc-muted">Publish empty seats on a route you already drive — passengers pay their share only.</p>
        <div class="ditto-steps"><span class="is-on">1 Verify driver</span><span>2 Trip details</span></div>
        <div class="svc-two">
          <form class="svc-card" data-driver-form>
            <h2>Identity verification</h2>
            <p class="svc-muted">CoPilot requires DigiLocker KYC and a verified driving licence.</p>
            <label>Driving licence<input name="dl" placeholder="DL-0420110012345" /></label>
            <label>Vehicle number<input name="vrn" value="DL 01 AB 1234" /></label>
            <button class="svc-submit" type="submit">Continue to trip details</button>
          </form>
          <form class="svc-card" data-driver-trip hidden>
            <h2>Trip settings</h2>
            <div class="svc-pair">
              <label>From<input name="from" value="Cyber Hub, Gurugram" /></label>
              <label>To<input name="to" value="Noida Sector 62" /></label>
            </div>
            <label>Seats<input name="seats" type="number" min="1" value="2" /></label>
            <label>₹ / seat<input name="fare" type="number" min="1" value="180" /></label>
            <button class="svc-submit" type="submit">Publish trip</button>
          </form>
        </div>
      </div>
      <div data-ride-view="passenger" hidden>
        <button class="svc-back" type="button" data-ride="home"><span class="mi">arrow_back</span>CoPilot</button>
        <p class="svc-kicker">Passenger</p>
        <h1>Before you book</h1>
        <p class="svc-muted">Emergency contact and profile-sharing consent are required for CoPilot rides.</p>
        <form class="svc-card ditto-narrow">
          <label>Emergency contact name<input name="ename" required placeholder="Contact name" /></label>
          <label>Emergency contact phone<input name="ephone" required placeholder="10-digit mobile" /></label>
          <label>Profile photo URL (optional)<input name="photo" placeholder="https://" /></label>
          <label class="ditto-check"><input type="checkbox" required /> I consent to share my verified profile with matched drivers for this trip.</label>
          <button class="svc-submit" type="submit">Save passenger profile</button>
        </form>
      </div>
    </section>`;
}

function transactionsScreen() {
  const rows = [
    ["24 Nov 2026", "FASTag recharge", "DL 01 AB 1234 · ICICI", "₹500", "Paid"],
    ["22 Nov 2026", "Parking", "Cyber Hub, Gurugram", "₹120", "Active"],
    ["18 Nov 2026", "Electricity", "BSES Rajdhani", "₹2,140", "Paid"],
    ["12 Nov 2026", "Challan", "DL 8C AX 4410", "₹1,000", "Due"],
  ]
    .map(
      ([when, service, ref, amount, status]) => `
      <div class="svc-txn" data-txn>
        <span>${when}</span><strong>${service}</strong><span>${ref}</span><b>${amount}</b><em class="svc-pill">${status}</em>
      </div>`,
    )
    .join("");
  return `
    <section class="svc svc-tx">
      <header class="svc-tx-hero">
        <div>
          <span class="svc-secure"><span class="mi">verified_user</span>Secure payment activity</span>
          <h1>Transaction history</h1>
          <p>Payments, bill pay, challans, vouchers and Connect orders in one place.</p>
          <a href="#dashboard">Back to dashboard</a>
        </div>
        <div class="svc-tx-stats">
          <article><span class="mi">payments</span><strong>₹3,760</strong><small>This month</small></article>
          <article><span class="mi">check_circle</span><strong>3</strong><small>Paid</small></article>
          <article><span class="mi">schedule</span><strong>1</strong><small>Due</small></article>
          <article><span class="mi">bolt</span><strong>1</strong><small>Active</small></article>
        </div>
      </header>
      <label class="svc-search svc-search-lg"><span class="mi">search</span><input type="search" data-txn-search placeholder="Search transactions" /></label>
      <div class="svc-card svc-tx-table">
        <div class="svc-txn svc-txn-head"><span>When</span><span>Service</span><span>Reference</span><span>Amount</span><span>Status</span></div>
        ${rows}
      </div>
    </section>`;
}

function connectScreen() {
  const vehicle = (number, name, on) =>
    `<button type="button" class="svc-vrow${on ? " is-on" : ""}" data-vehicle data-number="${number}" data-name="${name}" data-rc="${on ? "Valid" : "Valid"}" data-ins="${on ? "Valid" : "Expired"}" data-puc="${on ? "18 days" : "Valid"}" data-qr="${on ? "Active · 12 scans" : "Not issued"}"><strong>${number}</strong><small>${name}</small></button>`;
  return `
    <section class="svc svc-connect">
      <div data-connect-view="hub">
      <header class="svc-connect-head">
        <div><h1>Connect Hub</h1><p>Vehicles, QR stickers, chat &amp; calls</p></div>
        <button type="button" data-connect="add"><span class="mi">add</span>Add vehicle</button>
      </header>
      <nav class="svc-tabs" aria-label="Connect sections">
        <button type="button" class="is-on" data-tab="vehicles">Vehicles &amp; QR <span>2</span></button>
        <button type="button" data-tab="inbox">Chat</button>
        <button type="button" data-tab="calls">Calls</button>
      </nav>
      <div data-panel="vehicles" class="svc-connect-grid">
        <aside class="svc-card">
          <p class="svc-kicker svc-kicker-dark">Your vehicles</p>
          ${vehicle("DL 01 AB 1234", "Hyundai Creta", true)}
          ${vehicle("HR 26 DK 9081", "Maruti Suzuki Swift", false)}
        </aside>
        <div class="svc-connect-main">
          <article class="svc-card">
            <p class="svc-kicker svc-kicker-dark">Selected vehicle</p>
            <h2 data-connect-number>DL 01 AB 1234</h2>
            <p data-connect-name>Hyundai Creta</p>
            <div class="svc-pills">
              <span>RC · <b data-connect-rc>Valid</b></span>
              <span>QR · <b data-connect-qr>Active · 12 scans</b></span>
              <span>Connect · On</span>
            </div>
            <div class="svc-compliance">
              <div><small>RC / Fitness</small><strong data-connect-rc>Valid</strong></div>
              <div><small>Insurance</small><strong data-connect-ins>Valid</strong></div>
              <div><small>PUC</small><strong data-connect-puc>18 days</strong></div>
            </div>
          </article>
          <div class="svc-actions">
            <button type="button" data-connect="detail"><span class="mi">badge</span>Vehicle detail</button>
            <button type="button"><span class="mi">link</span>Copy link</button>
            <button type="button" data-connect="sticker"><span class="mi">local_shipping</span>Order sticker</button>
          </div>
          <div class="svc-wallets">
            <article><small>Wallet</small><strong>₹1,250.00</strong><a href="#parkpe-voucher">+ Recharge</a></article>
            <article><small>Voice rate</small><strong>₹2<small>/min</small></strong></article>
          </div>
          <article class="svc-card">
            <h3>Sticker preview</h3>
            <p class="svc-muted">100mm windshield layout — virtual QR with the vehicle number printed.</p>
            <div class="svc-sticker"><span class="mi">qr_code_2</span><strong data-connect-number>DL 01 AB 1234</strong></div>
          </article>
        </div>
      </div>
      <div data-panel="inbox" hidden>
        <div class="ditto-inbox">
          <aside class="svc-card">
            <header><h2>Chats</h2></header>
            <button type="button" class="is-on" data-thread><b>P</b><span><strong>DL 01 AB 1234</strong><small>Parking marshal · 2m</small></span></button>
            <button type="button" data-thread data-who="Gate" data-body="Please move to bay A4."><b>G</b><span><strong>HR 26 DK 9081</strong><small>Gate · 1h</small></span></button>
          </aside>
          <section class="svc-card ditto-thread">
            <header><b>P</b><div><strong data-thread-who>Parking marshal</strong><small>End-to-end with your vehicle QR</small></div></header>
            <div class="ditto-log">
              <p data-thread-body>Your bay at Cyber Hub is ready.</p>
              <p class="is-me">On my way.</p>
            </div>
            <form data-thread-form><input name="body" placeholder="Message" /><button type="submit">Send</button></form>
          </section>
        </div>
      </div>
      <div data-panel="calls" class="svc-empty" hidden><span class="mi">call</span><p>No calls yet</p></div>
      </div>
      <div data-connect-view="add" hidden>
        <button class="svc-back" type="button" data-connect="hub"><span class="mi">arrow_back</span>Connect hub</button>
        <h1>Add vehicle</h1>
        <p class="svc-muted">We verify your registration certificate (RC) against official records first. Your vehicle is added to your fleet only after verification succeeds.</p>
        <ol class="ditto-steps"><li class="is-on">1 Number</li><li>2 Verify RC</li><li>3 Add to fleet</li></ol>
        <form class="svc-card" data-rc-form data-rc-input>
          <label>Registration number (VRN)<input name="vrn" required placeholder="DL01AB1234" autocomplete="off" value="DL01AB1234" /></label>
          <p class="svc-muted">As printed on your RC — spaces optional.</p>
          <button class="svc-submit" type="submit">Verify RC</button>
        </form>
        <section class="svc-card ditto-ok" data-rc-ok hidden>
          <p class="svc-pill">RC verified — sample record</p>
          <h2 data-rc-vrn>DL01AB1234</h2>
          <ul class="ditto-rc">
            <li><span>Model</span> Hyundai Creta</li>
            <li><span>Fuel</span> Petrol</li>
            <li><span>Registered</span> 14 Mar 2022</li>
            <li><span>Owner (RC)</span> ParkPe User</li>
            <li><span>Insurance valid until</span> 18 Dec 2026</li>
            <li><span>PUC</span> 18 days left</li>
          </ul>
          <p class="svc-muted">Live RC lookup is not connected. Nothing is written to a fleet.</p>
          <button type="button" class="svc-submit" data-connect="detail">Open vehicle</button>
        </section>
      </div>
      <div data-connect-view="detail" hidden>
        <button class="svc-back" type="button" data-connect="hub"><span class="mi">arrow_back</span>Connect hub</button>
        <h1 data-connect-name>Hyundai Creta</h1>
        <p><b data-connect-number>DL 01 AB 1234</b> <span class="svc-pill">Valid</span></p>
        <section class="svc-card">
          <h2>Renewal dates</h2>
          <div class="ditto-fit">
            <article><small>RC validity</small><strong data-connect-rc>Valid</strong><p>Fitness on record</p></article>
            <article><small>Insurance</small><strong data-connect-ins>Valid</strong><p>Check the date on the policy</p></article>
            <article><small>PUC</small><strong data-connect-puc>18 days</strong><p>Renew before it lapses</p></article>
          </div>
        </section>
        <section class="svc-card">
          <h2>RC details</h2>
          <ul class="ditto-rc">
            <li><span>Maker model</span> Hyundai Creta</li>
            <li><span>Fuel</span> Petrol</li>
            <li><span>Owner</span> ParkPe User</li>
          </ul>
        </section>
      </div>
      <div data-connect-view="sticker" hidden>
        <button class="svc-back" type="button" data-connect="hub"><span class="mi">arrow_back</span>Connect hub</button>
        <h1>Order Connect QR sticker</h1>
        <p class="svc-muted">Physical weather-resistant label with your vehicle’s Connect QR. Shipped to your address.</p>
        <form class="svc-card">
          <h2>1. Product &amp; delivery</h2>
          <label>Product<select name="product"><option>Windshield QR — ₹149</option><option>Bumper QR — ₹129</option></select></label>
          <label>Quantity<input name="qty" type="number" min="1" max="20" value="1" /></label>
          <label>Link to vehicle<select><option>DL 01 AB 1234</option><option>HR 26 DK 9081</option><option>None</option></select></label>
          <h3>Shipping</h3>
          <div class="svc-pair">
            <label>Full name<input name="name" value="ParkPe User" /></label>
            <label>Phone<input name="phone" value="9800000010" /></label>
          </div>
          <label>Address line 1<input name="line1" placeholder="House, street" /></label>
          <label>Address line 2<input name="line2" placeholder="Area" /></label>
          <div class="svc-pair">
            <label>City<input name="city" value="Gurugram" /></label>
            <label>State<input name="state" value="Haryana" /></label>
            <label>PIN<input name="pin" value="122002" /></label>
          </div>
          <h3>Payment method</h3>
          <label class="ditto-check"><input type="radio" name="pm" checked /> Card / UPI / Netbanking</label>
          <label class="ditto-check"><input type="radio" name="pm" /> ParkPe voucher</label>
          <p>Estimated total: <strong>₹149.00</strong></p>
          <button class="svc-submit" type="submit">Place sticker order</button>
        </form>
      </div>
    </section>`;
}

function parkingScreen() {
  const tile = (view, title, text, badge, meta, iconName) => `
    <button type="button" class="svc-park-tile" data-park="${view}">
      <div><span class="mi">${iconName}</span><b>${badge}</b></div>
      <h2>${title}</h2>
      <p>${text}</p>
      <footer><span>${meta}</span><span class="mi">arrow_forward</span></footer>
    </button>`;
  return `
    <section class="svc">
      <div data-park-view="hub">
        <div class="svc-lime svc-park">
          <p class="svc-kicker">Parking desk</p>
          <h1>Customer parking</h1>
          <p>Book slots, monitor live occupancy and review history — counter flows only.</p>
        </div>
        <div class="svc-park-tiles">
          ${tile("book", "Book Parking", "Create a new parking booking and collect customer payment.", "New booking", "2 min setup", "local_parking")}
          ${tile("slots", "Active Slots", "Check occupied, available and expiring parking slots.", "Live status", "12 slots active", "grid_view")}
          ${tile("history", "Parking History", "Review completed bookings, receipts and customer records.", "Reports", "Last 30 days", "history")}
        </div>
        <div class="svc-split">
          <section class="svc-card">
            <h2>Parking Guidelines</h2>
            <div class="svc-guides">
              <p>Verify vehicle number before creating a booking.</p>
              <p>Confirm slot availability with the customer before payment.</p>
              <p>Keep receipt or booking ID for customer support.</p>
              <p>Close active slots after vehicle exit to avoid mismatch.</p>
            </div>
          </section>
          <aside class="svc-desk">
            <h2>Desk note</h2>
            <p>Use parking service only after confirming customer details, vehicle type and expected duration. Failed or duplicate payments should be checked from transaction history before retrying.</p>
            <div><span><strong>Fast</strong><small>Booking</small></span><span><strong>Live</strong><small>Slots</small></span><span><strong>Easy</strong><small>Receipt</small></span></div>
          </aside>
        </div>
      </div>
      <div data-park-view="book" hidden>
        <div class="ditto-book-head">
          <button class="svc-back" type="button" data-park="hub"><span class="mi">arrow_back</span>Parking</button>
          <div>
            <p class="svc-kicker">Retailer</p>
            <h1>Book Parking</h1>
            <p class="svc-muted">Pincode search, then location, vehicle, entry time and duration, then a quote and QR slip.</p>
          </div>
        </div>
        <section class="svc-card ditto-pass" data-book-slip hidden>
          <p class="svc-kicker">Payment sample</p>
          <h2>Your parking pass</h2>
          <p>Cyber Hub, Gurugram · <span data-slip-vehicle>DL 01 AB 1234</span> · ₹120</p>
          <div class="ditto-slip">
            <span class="mi">qr_code_2</span>
            <div>
              <p>Booking ID: <b>PK-20481</b></p>
              <p>Entry from: <b>Today, 4:10 PM</b></p>
              <p>Valid until: <b>Today, 8:30 PM</b></p>
            </div>
          </div>
        </section>
        <div class="ditto-book-grid">
          <div>
            <div class="svc-card ditto-steps">
              <span data-book-step="1" class="is-on">1 Pincode</span>
              <span data-book-step="2">2 Parking point</span>
              <span data-book-step="3">3 Vehicle &amp; window</span>
            </div>
            <section class="svc-card" data-book-card="1">
              <h2>Step 1 — Area pincode</h2>
              <p class="svc-muted">Search loads sample locations. Live ParkPe parking API is not connected.</p>
              <div class="ditto-pinrow">
                <label>Pincode<input data-book-pin inputmode="numeric" maxlength="8" placeholder="e.g. 122002" value="122002" /></label>
                <button type="button" data-pin-search>Search</button>
              </div>
            </section>
            <section class="svc-card is-dim" data-book-card="2">
              <h2>Step 2 — Parking points</h2>
              <p class="svc-muted">Choose a location.</p>
              <div class="ditto-points" data-points hidden>
                <button type="button" data-point="Cyber Hub, Gurugram"><strong>Cyber Hub</strong><span>Gurugram · <b data-point-pin>122002</b></span><small>Cap car 120 · bike 40</small></button>
                <button type="button" data-point="DLF Cyber City"><strong>DLF Cyber City</strong><span>Gurugram · <b data-point-pin>122002</b></span><small>Cap car 80 · bike 20</small></button>
                <button type="button" data-point="Select Citywalk"><strong>Select Citywalk</strong><span>Delhi · <b data-point-pin>122002</b></span><small>Cap car 60 · bike 15</small></button>
              </div>
            </section>
            <form class="svc-card is-dim" data-book-card="3" data-book-form>
              <h2>Step 3 — Vehicle, entry time &amp; duration</h2>
              <div class="svc-pair">
                <label>Vehicle number<input name="vehicle" value="DL01AB1234" /></label>
                <label>Vehicle type<select name="vtype"><option>Car</option><option>SUV</option><option>Bike</option></select></label>
              </div>
              <label>Entry window starts<input name="from" type="datetime-local" /></label>
              <label>Duration<select name="hours"><option value="1">1 hour</option><option value="2" selected>2 hours</option><option value="4">4 hours</option></select></label>
              <button class="svc-submit" type="submit">Get quote</button>
            </form>
          </div>
          <aside class="svc-card ditto-summary">
            <h2>Booking summary</h2>
            <dl>
              <div><dt>Parking point</dt><dd data-sum-point>—</dd></div>
              <div><dt>Vehicle type</dt><dd>Car</dd></div>
              <div><dt>Vehicle</dt><dd>DL01AB1234</dd></div>
              <div><dt>Duration</dt><dd>2 hours</dd></div>
              <div><dt>Est. rate / hr</dt><dd>₹60</dd></div>
              <div><dt>Quote</dt><dd>₹120</dd></div>
            </dl>
          </aside>
        </div>
      </div>
      <div data-park-view="slots" hidden>
        <button class="svc-back" type="button" data-park="hub"><span class="mi">arrow_back</span>Parking</button>
        <div class="svc-card svc-slot-head"><p class="svc-kicker">Live Status</p><h1>Active Slots</h1></div>
        <div class="svc-card ditto-slots">
          <article><header><strong>B12</strong><span class="svc-pill">Active</span></header><p>Cyber Hub · DL 01 AB 1234 · until 8:30 PM</p></article>
          <article><header><strong>A4</strong><span class="svc-pill">Expiring</span></header><p>DLF Cyber City · HR 26 DK 9081 · until 6:10 PM</p></article>
          <article><header><strong>C2</strong><span class="svc-pill">Active</span></header><p>Select Citywalk · DL 8C AX 4410 · until 9:00 PM</p></article>
          <article><header><strong>P1</strong><span class="svc-pill">Available</span></header><p>Cyber Hub · open bay</p></article>
        </div>
      </div>
      <div data-park-view="history" hidden>
        <button class="svc-back" type="button" data-park="hub"><span class="mi">arrow_back</span>Parking</button>
        <h1>Parking history</h1>
        <p class="svc-muted">Past and active bookings on ParkPe.</p>
        <article class="svc-card ditto-history"><div><strong>Cyber Hub, Gurugram</strong><p>DL 01 AB 1234 · Active</p><small>Today, 4:10 PM – 8:30 PM</small></div><b>₹120</b></article>
        <article class="svc-card ditto-history"><div><strong>DLF Cyber City</strong><p>DL 01 AB 1234 · Paid</p><small>18 Nov 2026, 10:00 AM – 1:00 PM</small></div><b>₹180</b></article>
        <article class="svc-card ditto-history"><div><strong>Select Citywalk</strong><p>DL 8C AX 4410 · Due</p><small>12 Nov 2026, 2:00 PM – 5:00 PM</small></div><b>₹240</b></article>
      </div>
    </section>`;
}

function supportScreen() {
  return `
    <section class="svc">
      <div class="svc-card svc-support-head">
        <div><h1>Support</h1><p>Open a ticket for parking, payments, or general help.</p></div>
        <a href="#dashboard">← Dashboard</a>
      </div>
      <form class="svc-card svc-support-form">
        <select name="topic"><option value="general">General</option><option value="parking">Parking</option><option value="payment">Payment</option></select>
        <input name="subject" required placeholder="Subject" />
        <textarea name="details" rows="3" placeholder="Describe the issue"></textarea>
        <button class="svc-submit" type="submit">Submit ticket</button>
      </form>
      <section class="svc-card">
        <h2>Your tickets</h2>
        <article class="svc-ticket"><div><strong>FASTag receipt not received</strong><span>OPEN</span></div><p>Payment · 12 Nov 2026</p></article>
      </section>
    </section>`;
}

function settingsScreen() {
  return `
    <section class="svc">
      <div class="svc-card svc-settings-hero">
        <p class="svc-kicker">Account settings</p>
        <h2>Security layers</h2>
        <p>Review enabled security layers. Updates are confirmed through secured API endpoints.</p>
      </div>
      <div class="svc-layers">
        <article><p>M-PIN</p><strong>Disabled</strong><small>4 digit step-up verification for locked sessions and sensitive actions.</small></article>
        <article><p>Authenticator App</p><strong>Disabled</strong><small>Time-based verification code from the user authenticator app.</small></article>
        <article><p>OTP Delivery</p><strong>Requires profile update</strong><small>One-time password delivery preference managed from the profile page.</small></article>
      </div>
    </section>`;
}

function profileScreen() {
  return `
    <section class="svc pf">
      <div class="pf-banner">
        <img src="../assets/img/landing-page/parking-location.svg" alt="" />
        <div class="pf-id">
          <label class="pf-photo">PU<input type="file" accept="image/*" data-photo hidden /></label>
          <div>
            <h1>ParkPe User</h1>
            <p><span class="mi">mail</span> user@parkpe.in</p>
            <p><span class="mi">call</span> +91 98000 00010</p>
            <div class="pf-chips"><span><span class="mi">person</span> Customer</span><span><span class="mi">check</span> Email on file</span></div>
          </div>
        </div>
        <button type="button" class="pf-meter" data-profile="address">
          <span class="pf-ring">67%</span>
          <span><strong>Profile Complete</strong><small>Complete your details so your ParkPe account stays accurate.</small></span>
          <i></i>
          <em><span class="mi">work</span> 2 items incomplete</em>
        </button>
      </div>
      <div class="pf-tabs">
        <button type="button" class="is-on" data-tab="overview"><span class="mi">dashboard</span>Overview</button>
        <button type="button" data-tab="personal"><span class="mi">person</span>Personal</button>
        <button type="button" data-tab="address"><span class="mi">location_on</span>Address</button>
        <button type="button" data-tab="security"><span class="mi">shield</span>Security</button>
      </div>
      <div data-panel="overview">
        <div class="pf-cards">
          <article><span class="mi tone-park">local_parking</span><strong>Parking</strong><small>Bookings &amp; history</small></article>
          <article><span class="mi tone-tag">toll</span><strong>FASTag</strong><small>Recharge &amp; trips</small></article>
          <article><span class="mi tone-bill">receipt_long</span><strong>BBPS</strong><small>Bill payments</small></article>
          <article><span class="mi tone-wallet">account_balance_wallet</span><strong>Wallet</strong><small>Balance &amp; methods</small></article>
        </div>
        <div class="pf-split">
          <section class="svc-card">
            <h2>Completion Checklist</h2>
            <ul class="pf-check">
              <li class="is-done"><span></span>Full name added</li>
              <li class="is-done"><span></span>Mobile number</li>
              <li class="is-done"><span></span>Email on account</li>
              <li class="is-done"><span></span>Vehicle details</li>
              <li><span></span>Address line &amp; PIN <button type="button" data-profile="address">Fix →</button></li>
              <li><span></span>City &amp; state <button type="button" data-profile="address">Fix →</button></li>
            </ul>
          </section>
          <section class="svc-card">
            <h2>Quick Actions</h2>
            <button type="button" data-profile="personal"><span class="mi">person</span><span><strong>Update personal details</strong><small>Name, mobile, vehicle</small></span></button>
            <button type="button" data-profile="address"><span class="mi">location_on</span><span><strong>Complete address</strong><small>PIN, city, state</small></span></button>
            <button type="button" data-profile="security"><span class="mi">shield</span><span><strong>OTP &amp; security</strong><small>Delivery channel for login codes</small></span></button>
          </section>
        </div>
      </div>
      <form class="svc-card" data-panel="personal" hidden>
        <h2>Personal Information</h2>
        <div class="pf-photo-row">
          <span>PU</span>
          <label class="svc-submit">Change Photo<input type="file" accept="image/*" data-photo hidden /></label>
          <p>Preview updates instantly above. Photos are not saved to your account yet — only this browser session.</p>
        </div>
        <div class="svc-pair">
          <label>Full Name<input name="fullName" value="ParkPe User" /></label>
          <label>Mobile Number<input name="mobile" value="9800000010" /></label>
          <label class="ditto-span">Email<input name="email" value="user@parkpe.in" readonly /><small>Email cannot be changed from here</small></label>
          <label>Vehicle Name<input name="vehicleName" value="Hyundai Creta" /></label>
          <label>Vehicle Number<input name="vehicleNumber" value="DL 01 AB 1234" /></label>
        </div>
        <button class="svc-submit" type="submit">Save Personal Info</button>
      </form>
      <form class="svc-card" data-panel="address" hidden>
        <h2>Address Details</h2>
        <label>Address Line 1<input name="addressLine1" placeholder="House/flat, street" /></label>
        <label>Address Line 2 <small>(optional)</small><input name="addressLine2" placeholder="Landmark, area" /></label>
        <div class="ditto-pinrow">
          <label>Pincode<input name="pincode" placeholder="6-digit PIN" /></label>
          <button type="button" disabled title="PIN lookup is not connected yet">Lookup</button>
          <label>City<input name="city" placeholder="City" /></label>
        </div>
        <div class="svc-pair">
          <label>State<input name="state" placeholder="State" /></label>
          <label>Country<input name="country" value="India" /></label>
        </div>
        <button class="svc-submit" type="submit">Save Address</button>
      </form>
      <div data-panel="security" hidden>
        <section class="svc-card">
          <h2>Account password</h2>
          <p class="svc-muted">Forgot your password? We can email a secure link to user@parkpe.in. The message does not confirm whether the account exists.</p>
          <div class="ditto-row">
            <button type="button" data-reset="email">Email me a reset link</button>
            <button type="button" data-reset="sms">SMS OTP to my mobile</button>
          </div>
        </section>
        <form class="svc-card">
          <h2>OTP delivery preference</h2>
          <p class="svc-muted">Choose where login OTP should be delivered. You can change this any time.</p>
          <div class="pf-otp">
            <label><input type="radio" name="otp" value="email" checked /> Email</label>
            <label><input type="radio" name="otp" value="sms" /> SMS</label>
            <label><input type="radio" name="otp" value="push" /> Push Notifications</label>
            <label><input type="radio" name="otp" value="both" /> SMS + Email</label>
          </div>
          <button class="svc-submit" type="submit">Save OTP preference</button>
        </form>
        <form class="svc-card">
          <h2>Transaction PIN (TPIN) requirement</h2>
          <p class="svc-muted">When enabled, payments that debit your ParkPe wallet require your TPIN. ParkPe voucher payments use your voucher PIN instead.</p>
          <label class="ditto-check"><input type="checkbox" checked /> Require TPIN for wallet debits</label>
          <button class="svc-submit" type="submit">Save TPIN requirement</button>
        </form>
        <form class="svc-card">
          <h2>Session &amp; transaction PINs</h2>
          <p class="svc-muted"><strong>Session PIN</strong> — 4 digits to sign in again after your browser session expires. <strong>TPIN</strong> — separate 4 digits for wallet debits.</p>
          <label>Account password<input type="password" name="password" autocomplete="current-password" /></label>
          <div class="svc-two">
            <div>
              <h3>Session re-login PIN</h3>
              <p class="svc-muted">4 digits. Avoid repeats such as 1111.</p>
              <input type="password" name="session" maxlength="4" inputmode="numeric" />
              <div class="ditto-row">
                <button class="svc-submit" type="submit">Save session PIN</button>
                <button type="button" data-clear-pin="session">Remove session PIN</button>
              </div>
            </div>
            <div>
              <h3>Transaction PIN (TPIN)</h3>
              <p class="svc-muted">Used for wallet debits. Different from session PIN and voucher PIN.</p>
              <input type="password" name="tpin" maxlength="4" inputmode="numeric" />
              <div class="ditto-row">
                <button class="svc-submit" type="submit">Save TPIN</button>
                <button type="button" data-clear-pin="tpin">Remove TPIN</button>
              </div>
            </div>
          </div>
        </form>
      </div>
    </section>`;
}

function notificationsScreen() {
  return `
    <section class="svc nt">
      <h1>Notifications</h1>
      <div class="nt-tabs">
        <button type="button" class="is-on" data-note-tab="all">All</button>
        <button type="button" data-note-tab="unread">Unread</button>
        <button type="button" data-note-tab="important">Important</button>
      </div>
      <ul>
        <li class="is-unread" data-note data-read="0" data-priority="important">
          <button type="button" data-go="dashboard"><strong>PUC expires in 18 days</strong><p>DL 01 AB 1234 · renew the certificate before it lapses.</p><small>vehicle · important</small></button>
          <button type="button" data-mark>Mark read</button>
        </li>
        <li class="is-unread" data-note data-read="0" data-priority="important">
          <button type="button" data-go="dashboard"><strong>Insurance has expired</strong><p>HR 26 DK 9081 · the policy date is in the past.</p><small>vehicle · important</small></button>
          <button type="button" data-mark>Mark read</button>
        </li>
        <li class="is-unread" data-note data-read="0" data-priority="normal">
          <button type="button" data-go="fastag"><strong>FASTag balance low</strong><p>HR 26 DK 9081 is below ₹200.</p><small>fastag · normal</small></button>
          <button type="button" data-mark>Mark read</button>
        </li>
        <li data-note data-read="1" data-priority="normal">
          <button type="button" data-go="parking"><strong>Parking session closed</strong><p>Cyber Hub · DL 01 AB 1234 · ₹120 paid.</p><small>parking · normal</small></button>
        </li>
      </ul>
    </section>`;
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

function challanTotal(root) {
  const picks = [...root.querySelectorAll("[data-challan-pick]")].filter((box) => box.checked);
  const total = picks.reduce((sum, box) => sum + Number(box.dataset.rupee || 0), 0);
  const label = `${picks.length} selected · ₹${total.toLocaleString("en-IN")}`;
  root.querySelectorAll("[data-challan-count]").forEach((node) => { node.textContent = label; });
}

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
  const voucher = event.target.closest("[data-voucher]");
  if (voucher && root.contains(voucher)) {
    root.querySelectorAll("[data-voucher-view]").forEach((node) => {
      node.hidden = node.dataset.voucherView !== voucher.dataset.voucher;
    });
    if (voucher.dataset.code) {
      const code = voucher.dataset.code;
      const amount = voucher.dataset.amount || "0.00";
      root.querySelectorAll("[data-v-code]").forEach((node) => { node.textContent = code; });
      root.querySelectorAll("[data-v-ref]").forEach((node) => { node.textContent = voucher.dataset.ref || ""; });
      root.querySelectorAll("[data-v-issued], [data-v-issued-row]").forEach((node) => {
        node.textContent = node.hasAttribute("data-v-issued-row") ? voucher.dataset.issued : `Created ${voucher.dataset.issued}`;
      });
      root.querySelectorAll("[data-v-status]").forEach((node) => { node.textContent = voucher.dataset.status || ""; });
      root.querySelectorAll("[data-v-balance]").forEach((node) => { node.textContent = `₹${amount}`; });
      root.querySelectorAll("[data-v-original]").forEach((node) => { node.textContent = `Original ₹${amount}`; });
      root.querySelectorAll("[data-v-ledger]").forEach((node) => { node.textContent = `+ Rs ${amount}`; });
    }
  }
  const amount = event.target.closest("[data-amount]");
  if (amount && root.contains(amount)) {
    const input = amount.parentElement.parentElement.querySelector("[data-amount-input]");
    if (input) input.value = amount.dataset.amount;
    amount.parentElement.querySelectorAll("[data-amount]").forEach((button) => button.classList.toggle("is-on", button === amount));
  }
  const pin = event.target.closest("[data-pin]");
  if (pin && root.contains(pin)) {
    const input = pin.parentElement.querySelector("[data-pin-input]");
    const shown = input.type === "text";
    input.type = shown ? "password" : "text";
    pin.querySelector(".mi").textContent = shown ? "visibility" : "visibility_off";
  }
  const park = event.target.closest("[data-park]");
  if (park && root.contains(park)) {
    root.querySelectorAll("[data-park-view]").forEach((node) => {
      node.hidden = node.dataset.parkView !== park.dataset.park;
    });
  }
  const offer = event.target.closest("[data-offer]");
  if (offer && root.contains(offer)) {
    const form = root.querySelector("[data-offer-form]");
    form.hidden = !form.hidden;
  }
  const vehicle = event.target.closest("[data-vehicle]");
  if (vehicle && root.contains(vehicle)) {
    root.querySelectorAll("[data-vehicle]").forEach((row) => row.classList.toggle("is-on", row === vehicle));
    ["number", "name", "rc", "ins", "puc", "qr"].forEach((key) => {
      root.querySelectorAll(`[data-connect-${key}]`).forEach((node) => {
        node.textContent = vehicle.dataset[key];
      });
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
    const board = op.closest(".op-board") || op.closest("form") || root;
    board.querySelectorAll("[data-op]").forEach((item) => item.classList.toggle("is-on", item === op));
    const current = root.querySelector("[data-op-current]");
    if (current) current.textContent = op.dataset.op;
    const mark = root.querySelector("[data-op-mark]");
    if (mark && !mark.querySelector("img")) mark.textContent = op.dataset.op.trim().charAt(0);
    const logo = root.querySelector("[data-op-logo]");
    const img = op.querySelector("img");
    if (logo && img) logo.src = img.src;
  }
  if (event.target.closest("[data-bill-pay]") || event.target.closest("[data-brand-pay]")) {
    root.querySelector("[data-step='pay']")?.classList.add("is-on");
    root.querySelector("[data-step='done']")?.classList.add("is-on");
    toast("Payment stays on this screen until the service API is connected.");
  }
  const filter = event.target.closest("[data-brand-filter]");
  if (filter) {
    filter.parentElement.querySelectorAll("[data-brand-filter]").forEach((button) => {
      button.classList.toggle("is-on", button === filter);
    });
    applyBrandFilters(root);
  }
  const buy = event.target.closest("[data-brand-buy]");
  if (buy && root.contains(buy)) {
    const sheet = root.querySelector("[data-brand-sheet]");
    sheet.hidden = false;
    sheet.querySelector("[data-brand-name]").textContent = `${buy.dataset.brandBuy} voucher`;
    sheet.querySelector("[data-brand-off]").textContent = `Save ${buy.dataset.off}% on this purchase`;
    const mark = sheet.querySelector("[data-brand-mark]");
    mark.textContent = buy.dataset.initial;
    mark.style.background = buy.dataset.color;
    const amounts = buy.dataset.amounts.split(",");
    sheet.querySelector("[data-denoms]").innerHTML = amounts
      .map((value, index) => `<button type="button" class="svc-denom${index === 0 ? " is-on" : ""}" data-denom="${value}">Rs ${value}</button>`)
      .join("");
  }
  const denom = event.target.closest("[data-denom]");
  if (denom) {
    denom.parentElement.querySelectorAll("[data-denom]").forEach((button) => button.classList.toggle("is-on", button === denom));
  }
  if (event.target.closest("[data-brand-close]") || event.target.matches("[data-brand-sheet]")) {
    const sheet = root.querySelector("[data-brand-sheet]");
    if (sheet) sheet.hidden = true;
  }
  const go = event.target.closest("[data-go]");
  if (go) location.hash = go.dataset.go;
  const named = event.target.closest("[data-connect], [data-ride]");
  if (named && root.contains(named)) {
    const kind = named.hasAttribute("data-connect") ? "connect" : "ride";
    const value = named.dataset[kind];
    root.querySelectorAll(`[data-${kind}-view]`).forEach((node) => {
      node.hidden = node.dataset[`${kind}View`] !== value;
    });
    if (kind === "ride" && named.dataset.when) {
      root.querySelectorAll("[data-trip-price]").forEach((node) => { node.textContent = `₹${named.dataset.price}`; });
      root.querySelectorAll("[data-trip-driver]").forEach((node) => { node.textContent = named.dataset.driver || ""; });
      root.querySelectorAll("[data-trip-when]").forEach((node) => { node.textContent = `25 Nov 2026 · ${named.dataset.when}`; });
      root.querySelectorAll("[data-trip-seats]").forEach((node) => { node.textContent = named.dataset.seats || ""; });
    }
  }
  if (event.target.closest("[data-ride-book]")) {
    toast("Seat request stays on this screen until the CoPilot API is connected.");
  }
  const noteTab = event.target.closest("[data-note-tab]");
  if (noteTab && root.contains(noteTab)) {
    noteTab.parentElement.querySelectorAll("[data-note-tab]").forEach((button) => {
      button.classList.toggle("is-on", button === noteTab);
    });
    const mode = noteTab.dataset.noteTab;
    root.querySelectorAll("[data-note]").forEach((card) => {
      const unread = card.dataset.read !== "1";
      const important = card.dataset.priority === "important";
      card.hidden = (mode === "unread" && !unread) || (mode === "important" && !important);
    });
  }
  const mark = event.target.closest("[data-mark]");
  if (mark && root.contains(mark)) {
    const card = mark.closest("[data-note]");
    card.dataset.read = "1";
    card.classList.remove("is-unread");
    mark.remove();
    const active = root.querySelector("[data-note-tab].is-on");
    if (active && active.dataset.noteTab === "unread") card.hidden = true;
  }
  if (event.target.closest("[data-challan-all]")) {
    const on = event.target.closest("[data-challan-all]").checked;
    root.querySelectorAll("[data-challan-pick]").forEach((box) => { box.checked = on; });
    challanTotal(root);
  }
  if (event.target.closest("[data-challan-pick]")) challanTotal(root);
  if (event.target.closest("[data-challan-clear]")) {
    root.querySelectorAll("[data-challan-pick], [data-challan-all]").forEach((box) => { box.checked = false; });
    challanTotal(root);
  }
  if (event.target.closest("[data-challan-pay]")) {
    toast("Payment stays on this screen until the challan API is connected.");
  }
  const pinSearch = event.target.closest("[data-pin-search]");
  if (pinSearch && root.contains(pinSearch)) {
    const pin = root.querySelector("[data-book-pin]")?.value.trim() || "122002";
    const list = root.querySelector("[data-points]");
    list.hidden = false;
    list.querySelectorAll("[data-point-pin]").forEach((node) => { node.textContent = pin; });
    root.querySelectorAll("[data-book-step]").forEach((step) => {
      step.classList.toggle("is-on", Number(step.dataset.bookStep) <= 2);
    });
    root.querySelector("[data-book-card='2']")?.classList.remove("is-dim");
  }
  const point = event.target.closest("[data-point]");
  if (point && root.contains(point)) {
    root.querySelectorAll("[data-point]").forEach((card) => card.classList.toggle("is-on", card === point));
    root.querySelectorAll("[data-sum-point]").forEach((node) => { node.textContent = point.dataset.point; });
    root.querySelector("[data-book-card='3']")?.classList.remove("is-dim");
    root.querySelectorAll("[data-book-step]").forEach((step) => step.classList.add("is-on"));
  }
  const profileJump = event.target.closest("[data-profile]");
  if (profileJump && root.contains(profileJump)) {
    const id = profileJump.dataset.profile;
    const button = root.querySelector(`.pf-tabs [data-tab="${id}"]`);
    if (button) button.click();
  }
  const thread = event.target.closest("[data-thread]");
  if (thread && root.contains(thread)) {
    thread.parentElement.querySelectorAll("[data-thread]").forEach((row) => row.classList.toggle("is-on", row === thread));
    const who = root.querySelector("[data-thread-who]");
    const body = root.querySelector("[data-thread-body]");
    if (who && thread.dataset.who) who.textContent = thread.dataset.who;
    if (body && thread.dataset.body) body.textContent = thread.dataset.body;
  }
  if (event.target.closest("[data-reset], [data-clear-pin]")) {
    toast("Saved on this screen. It will sync when this service API is connected.");
  }
}

function onChange(event) {
  const file = event.target;
  if (!(file instanceof HTMLInputElement) || !file.matches("[data-photo]") || !file.files || !file.files[0]) return;
  const url = URL.createObjectURL(file.files[0]);
  event.currentTarget.querySelectorAll(".pf-photo, .pf-photo-row span").forEach((node) => {
    node.textContent = "";
    const img = document.createElement("img");
    img.alt = "";
    img.src = url;
    node.append(img);
  });
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
    const board = event.target.closest("form") || event.target.closest(".op-board") || root;
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
  if (event.target.matches("[data-brand-search]")) applyBrandFilters(root);
  if (event.target.matches("[data-txn-search]")) {
    const query = event.target.value.trim().toLowerCase();
    root.querySelectorAll("[data-txn]").forEach((row) => {
      row.hidden = query && !row.textContent.toLowerCase().includes(query);
    });
  }
  if (event.target.matches("[data-voucher-search]")) {
    const query = event.target.value.trim().toLowerCase();
    root.querySelectorAll("[data-voucher-row]").forEach((row) => {
      row.hidden = query && !row.textContent.toLowerCase().includes(query);
    });
  }
}

async function onSubmit(event) {
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
    const vehicle = esc(String(data.get("vehicle") || "Vehicle").toUpperCase().replace(/\s+/g, ""));
    const box = root.querySelector("[data-challan-results]");
    box.hidden = false;
    box.querySelectorAll("[data-challan-vehicle]").forEach((node) => { node.textContent = vehicle; });
    box.scrollIntoView({ block: "nearest" });
    return;
  }
  if (form.matches("[data-qr-form]")) {
    const box = root.querySelector("[data-qr-result]");
    box.hidden = false;
    box.innerHTML = `<strong>Parking slip</strong><p>Type: parking · Cyber Hub, bay B12</p><a href="#parking">Open in ParkPe</a>`;
    const site = String(data.get("site_code") || "").trim();
    const bay = String(data.get("bay") || "").trim();
    const vehicle = String(data.get("vehicle") || "").trim();
    if (site && bay && vehicle && globalThis.ParkpeHub) {
      const result = await globalThis.ParkpeHub.initiateSession(
        { site_code: site, bay, vehicle },
        crypto.randomUUID(),
      );
      const line = document.createElement("p");
      line.textContent = result.ok
        ? `Session ${result.data.reference} is ${result.data.state}.`
        : result.error;
      box.append(line);
    }
    return;
  }
  if (form.matches("[data-ride-form]")) {
    const from = String(data.get("from") || "");
    const to = String(data.get("to") || "");
    root.querySelectorAll("[data-ride-from]").forEach((node) => { node.textContent = from; });
    root.querySelectorAll("[data-ride-to]").forEach((node) => { node.textContent = to; });
    root.querySelectorAll("[data-ride-route]").forEach((node) => { node.textContent = `${from} → ${to}`; });
    root.querySelectorAll("[data-ride-view]").forEach((node) => {
      node.hidden = node.dataset.rideView !== "search";
    });
    return;
  }
  if (form.matches("[data-driver-form]")) {
    const next = root.querySelector("[data-driver-trip]");
    if (next) next.hidden = false;
    toast("Sample check only. DigiLocker is not connected.");
    return;
  }
  if (form.matches("[data-rc-form]")) {
    const vrn = String(data.get("vrn") || "DL01AB1234").toUpperCase().replace(/\s+/g, "");
    root.querySelectorAll("[data-rc-vrn]").forEach((node) => { node.textContent = vrn; });
    root.querySelector("[data-rc-input]")?.setAttribute("hidden", "");
    root.querySelector("[data-rc-ok]")?.removeAttribute("hidden");
    return;
  }
  if (form.matches("[data-book-form]")) {
    const slip = root.querySelector("[data-book-slip]");
    if (slip) slip.hidden = false;
    const vehicle = String(data.get("vehicle") || "DL 01 AB 1234");
    root.querySelectorAll("[data-slip-vehicle]").forEach((node) => { node.textContent = vehicle; });
    toast("Quote stays on this screen until the parking API is connected.");
    return;
  }
  if (form.matches("[data-offer-form]")) {
    toast("Trip stays on this screen until the CoPilot API is connected.");
    return;
  }
  if (form.closest("[data-voucher-view='balance']")) {
    root.querySelector("[data-balance-value]").textContent = "Rs 1250.00";
    root.querySelector("[data-balance-note]").textContent = "Sample balance for PP-20481. Live voucher lookup is not connected.";
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
      root.addEventListener("change", onChange);
      root.addEventListener("submit", onSubmit);
      wired = true;
    }
  },
};
})();
