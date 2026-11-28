/* PaySwap counter screens for apps/payswap/index.html.

   All balances, entitlements, BBPS transactions, and profile data come from
   PayswapHub (/api/v1/payswap/*) and PayswapSession (/api/auth/*).
   No sample or hardcoded ledger rows live here.
   ParkPe must not load this file.
*/
(function () {
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function icon(name) {
    return `<span class="mi">${name}</span>`;
  }

  function rupee(value) {
    const num = Number(value || 0);
    return "₹" + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
            <p class="kicker" data-home-outlet>Retailer counter</p>
            <h1 id="hello">Counter</h1>
            <p data-home-subtitle>Wallet float, assigned services, and the latest collections on this outlet.</p>
          </div>
          <a class="btn yellow" href="#bills" data-home-primary-cta>Collect BBPS bill</a>
        </header>
        <section class="stats" aria-label="Outlet metrics">
          <article class="stat">
            <span>Available wallet</span>
            <strong data-home-avail>₹0.00</strong>
            <em data-home-held>Held ₹0.00</em>
          </article>
          <article class="stat">
            <span>Daily debit used</span>
            <strong data-home-daily-used>₹0.00</strong>
            <em data-home-daily-limit>Limit ₹0.00</em>
          </article>
          <article class="stat">
            <span>Recent transactions</span>
            <strong data-home-txn-count>0</strong>
            <em data-home-txn-meta>Loading live ledger…</em>
          </article>
        </section>
        <section class="card">
          <div class="panel-head-inline">
            <h2>Assigned services</h2>
            <span class="hint" data-home-rails></span>
          </div>
          <div class="tiles" data-home-tiles></div>
        </section>
        <section class="card">
          <div class="panel-head-inline">
            <h2>Recent transactions</h2>
            <a class="text-link" href="#transactions" data-home-view-all>View all →</a>
          </div>
          <div data-home-txns><p class="hint">Loading recent transactions…</p></div>
        </section>
      </div>`;
  }

  function bills() {
    return `
      <div class="screen retail-bbps">
        <section class="bbps-topbar" data-bbps-connection aria-live="polite">
          <div class="bbps-brand-chip" aria-label="Bharat Connect">
            <img src="assets/bbps/bharat-connect-logo.svg" alt="Bharat Connect" />
          </div>
          <div class="bbps-status-left">
            <div class="bbps-check" aria-hidden="true"><span class="mi">check</span></div>
            <div>
              <strong data-bbps-connection-title>Checking BBPS connection</strong>
              <p data-bbps-connection-copy>Loading the secure biller catalogue…</p>
            </div>
          </div>
          <div class="bbps-top-metrics" aria-label="Counter snapshot">
            <div class="bbps-top-metric">
              <small>Wallet</small>
              <b data-bbps-wallet-chip>₹0.00</b>
            </div>
            <div class="bbps-top-metric">
              <small>Avg fetch</small>
              <b>&lt; 10s</b>
            </div>
          </div>
          <div class="bbps-connection-actions">
            <a class="btn subtle" href="#transactions"><span class="mi">history</span> Transactions</a>
            <button class="btn subtle" type="button" data-bbps-refresh><span class="mi">refresh</span> Refresh</button>
          </div>
        </section>

        <div class="bbps-steps" aria-label="Bill payment process">
          <div class="step is-current"><span>1</span><em>Select Category</em></div>
          <div class="step"><span>2</span><em>Choose Biller</em></div>
          <div class="step"><span>3</span><em>Fetch Bill</em></div>
          <div class="step"><span>4</span><em>Pay</em></div>
        </div>

        <div class="bbps-flow">
          <section class="bbps-col" data-bbps-col="category">
            <header class="bbps-col-head">
              <h2>Select Category</h2>
              <p data-bbps-scope-note>Pick a service to list billers.</p>
            </header>
            <div class="bbps-cat-list" data-bbps-cats><span class="hint">Loading categories…</span></div>
          </section>

          <section class="bbps-col" data-bbps-col="biller">
            <header class="bbps-col-head">
              <h2 data-bbps-biller-title>Choose Biller</h2>
              <p><span data-bbps-count>—</span> · <span data-bbps-category-name>Category</span></p>
            </header>
            <label class="retail-bbps-search">
              <span class="mi" aria-hidden="true">search</span>
              <input data-bbps-q type="search" placeholder="Search biller name, ID, or code..." aria-label="Search biller" />
              <button type="button" class="bbps-search-clear" data-bbps-clear-q hidden aria-label="Clear search"><span class="mi">close</span></button>
            </label>
            <div class="bbps-op-list" data-bbps-ops></div>
            <p class="empty-note hint" data-bbps-ops-empty>Select a category to load billers.</p>
          </section>

          <section class="bbps-col bbps-col-pay" data-bbps-col="pay">
            <div class="bbps-pay-empty" data-bill-empty>
              <header class="bbps-empty-head">
                <div class="bbps-bigicon" aria-hidden="true"><span class="mi">receipt_long</span></div>
                <div>
                  <h3>Ready to collect</h3>
                  <p>Pick a biller on the left, then fetch and pay here.</p>
                </div>
              </header>

              <div class="bbps-empty-cards">
                <article class="bbps-side-card bbps-side-card-wallet">
                  <div class="bbps-side-card-top">
                    <span class="mi" aria-hidden="true">account_balance_wallet</span>
                    <small>Available wallet</small>
                  </div>
                  <strong data-bbps-empty-wallet>₹0.00</strong>
                  <p data-bbps-empty-wallet-meta>Load float before peak hours</p>
                  <a class="bbps-side-link" href="#wallet">Add money →</a>
                </article>

                <article class="bbps-side-card">
                  <h4>How it works</h4>
                  <ol class="bbps-how">
                    <li><span>1</span>Select category</li>
                    <li><span>2</span>Choose biller</li>
                    <li><span>3</span>Fetch due bill</li>
                    <li><span>4</span>Pay via Wallet / PG</li>
                  </ol>
                </article>

                <article class="bbps-side-card">
                  <h4>Why Bharat Connect</h4>
                  <ul class="bbps-pay-tips">
                    <li><span class="mi">verified</span> Live bill fetch</li>
                    <li><span class="mi">payments</span> Wallet &amp; PG settlement</li>
                    <li><span class="mi">receipt_long</span> Instant receipt download</li>
                  </ul>
                </article>

                <article class="bbps-side-card bbps-side-card-recent">
                  <div class="bbps-side-card-top">
                    <h4>Recent collections</h4>
                    <a class="bbps-side-link" href="#transactions">All →</a>
                  </div>
                  <div class="bbps-recent-list" data-bbps-recent>
                    <p class="hint">Recent BBPS payments will show here.</p>
                  </div>
                </article>
              </div>
            </div>

            <form class="bbps-pay-form fields" data-bill-form hidden>
              <div class="picked">
                <span class="mark">
                  <img src="" alt="" data-bill-logo hidden />
                  <span class="mi" data-bill-glyph>receipt_long</span>
                </span>
                <div class="picked-copy">
                  <strong data-bill-title>Biller</strong>
                  <p class="hint" data-bill-biller></p>
                </div>
                <button type="button" class="btn subtle xs" data-bbps-clear-op>Change</button>
              </div>

              <div class="bbps-compose" data-bbps-compose>
                <div class="bbps-pay-block">
                  <h3>Enter Consumer Details</h3>
                  <label class="field">
                    <span class="bbps-field-top">
                      <span data-bbps-account-label>Consumer number</span>
                    </span>
                    <input name="account" required placeholder="Enter consumer number" autocomplete="off" />
                  </label>
                  <label class="field" data-bbps-cir-select-wrap hidden>
                    Telecom circle
                    <select name="circle" data-bbps-circle>
                      <option value="">Select circle</option>
                    </select>
                  </label>
                  <label class="field" data-bbps-cir-wrap hidden>
                    Circle / State ID
                    <input name="circle_manual" data-bbps-circle-manual placeholder="Circle code" autocomplete="off" />
                  </label>
                  <div class="fields" data-bbps-ad-params></div>
                  <button class="btn bbps-fetch-btn block" type="button" data-bbps-fetch hidden>
                    <span class="mi" aria-hidden="true">search</span> Fetch Bill
                  </button>
                  <button class="btn bbps-fetch-btn block" type="button" data-bbps-load-plans hidden>
                    <span class="mi" aria-hidden="true">list_alt</span> Refresh plans
                  </button>
                  <p class="hint" data-bbps-fetch-note></p>
                </div>

                <div class="bbps-plans-block" data-bbps-plans-wrap hidden>
                  <div class="bbps-plans-head">
                    <strong>Select a plan</strong>
                    <span class="hint" data-bbps-plans-count></span>
                  </div>
                  <div class="bbps-plan-tabs" data-bbps-plan-tabs hidden></div>
                  <div class="plans" data-bbps-plans></div>
                  <p class="hint" data-bbps-plans-empty hidden>No plans for this circle. Try another circle or enter amount manually.</p>
                </div>

                <div class="receipt bbps-receipt" data-bbps-bill-box hidden></div>

                <div class="bbps-pay-block">
                  <label class="field">Amount (₹)<input name="amount" inputmode="decimal" required placeholder="0.00" data-bbps-amount /></label>
                  <div class="fields two">
                    <label class="field">Customer mobile<input name="customer_mobile" inputmode="numeric" maxlength="10" placeholder="10-digit mobile" /></label>
                    <label class="field">BBPS mode
                      <select name="payment_mode"><option value="Cash">Cash</option></select>
                    </label>
                  </div>
                  <label class="field">Remitter name<input name="remitter_name" placeholder="Customer or counter name" /></label>
                </div>

                <div class="bbps-pay-block">
                  <h3>Payment Method</h3>
                  <div class="bbps-rails" data-bbps-rails></div>
                  <small class="hint" data-bbps-wallet-hint></small>
                  <label class="field" data-bbps-pin-wrap hidden>
                    Wallet PIN
                    <input name="wallet_pin" type="password" inputmode="numeric" maxlength="6" autocomplete="off" placeholder="4-6 digit Wallet PIN" />
                  </label>
                </div>

                <button class="btn bbps-pay-btn block" type="submit" data-bbps-pay-btn>
                  <span class="mi" aria-hidden="true">verified_user</span> <span data-bbps-pay-label>Pay bill</span>
                </button>
              </div>

              <div class="bbps-done" data-bbps-done hidden>
                <div class="bbps-done-badge" aria-hidden="true"><span class="mi">check_circle</span></div>
                <h3 data-bbps-done-title>Payment recorded</h3>
                <p data-bbps-done-copy>This bill is already submitted. Start a new collection for the next customer.</p>
              </div>

              <div class="bbps-status-box" data-bbps-status role="status" hidden></div>
              <div class="receipt bbps-receipt" data-bbps-pay-receipt hidden></div>
              <div class="receipt bbps-receipt" data-bbps-pg-box hidden></div>
              <div class="bbps-postpay-actions" data-bbps-postpay hidden>
                <button class="btn subtle" type="button" data-bbps-check-status>Check live status</button>
                <button class="btn subtle" type="button" data-bbps-print-receipt hidden>Download receipt</button>
                <a class="btn subtle" href="#transactions">View in Transactions</a>
                <button class="btn yellow" type="button" data-bbps-another>Pay another bill</button>
              </div>
            </form>
          </section>
        </div>
      </div>`;
  }

  function wallet() {
    return `
      <div class="screen">
        <header class="transaction-head">
          <div>
            <p class="kicker">Retailer wallet</p>
            <h1>Float &amp; Ledger</h1>
            <p>Live available float, active payment holds, daily spend limits, and double-entry ledger.</p>
          </div>
          <div class="wallet-head-actions">
            <button class="btn subtle" type="button" data-wallet-refresh>Refresh</button>
          </div>
        </header>
        <div class="wallet-banner-frozen" data-w-frozen-banner hidden>
          <div>
            <strong>Wallet is frozen</strong>
            <p data-w-frozen-reason>Contact your administrator to unfreeze wallet debits.</p>
          </div>
        </div>
        <div class="stats">
          <article class="stat"><span>Available balance</span><strong data-w-avail>₹0.00</strong><em data-w-status>Checking status…</em></article>
          <article class="stat"><span>Held for pending txns</span><strong data-w-held>₹0.00</strong><em>Released automatically if failed</em></article>
          <article class="stat"><span>Per-txn / Min reserve</span><strong data-w-pertxn>₹0.00</strong><em data-w-minbal>Min balance ₹0.00</em></article>
          <article class="stat"><span>MTD commission</span><strong data-w-comm>₹0.00</strong><em data-w-tds>TDS ₹0.00</em></article>
        </div>
        <section class="card">
          <div class="meter-copy"><span>Daily debit usage</span><span data-w-daily-copy>₹0.00 of ₹0.00</span></div>
          <div class="meter" aria-hidden="true"><span data-w-daily-bar style="width:0%"></span></div>
        </section>
        <div class="wallet-split">
          <form class="card fields" data-wallet-utr-form>
            <h2>Request float load (Bank / UPI UTR)</h2>
            <p class="hint">Submit your bank transfer or UPI UTR after transferring funds. Admin approval credits your wallet.</p>
            ${chips(["1000", "5000", "10000", "25000"], "5000")}
            <label class="field">Amount (₹)<input name="amount" value="5000" inputmode="decimal" required /></label>
            <label class="field">Mode
              <select name="mode">
                <option value="BANK_TRANSFER">IMPS / NEFT / RTGS</option>
                <option value="UPI">UPI</option>
              </select>
            </label>
            <label class="field">UTR / Reference number<input name="utr" required minlength="6" maxlength="64" placeholder="Enter bank UTR or UPI ref" autocomplete="off" /></label>
            <label class="field">Remarks (optional)<input name="remarks" maxlength="200" placeholder="Bank name or note" /></label>
            <button class="btn yellow" type="submit">Submit top-up request</button>
            <p class="preview-result" data-w-utr-status role="status" hidden></p>
          </form>
          <form class="card fields" data-wallet-pg-form hidden>
            <h2>Instant top-up via Payment Gateway</h2>
            <p class="hint" data-w-pg-hint>Add wallet float directly using UPI, Netbanking, or Card.</p>
            ${chips(["500", "1000", "2500", "5000"], "1000")}
            <label class="field">Amount (₹)<input name="amount" value="1000" inputmode="decimal" required /></label>
            <label class="field">Mobile (10-digit)<input name="customer_phone" inputmode="numeric" maxlength="10" placeholder="Optional" /></label>
            <button class="btn yellow" type="submit">Create PG top-up order</button>
            <p class="preview-result" data-w-pg-status role="status" hidden></p>
            <div class="receipt" data-w-pg-box hidden></div>
          </form>
        </div>
        <section class="card">
          <div class="panel-head-inline">
            <h2>PG top-up orders</h2>
            <span class="hint" data-w-pg-orders-count></span>
          </div>
          <div data-w-pg-orders><p class="hint">Loading PG orders…</p></div>
        </section>
        <section class="card">
          <div class="panel-head-inline">
            <h2>Top-up requests</h2>
            <span class="hint" data-w-topups-count></span>
          </div>
          <div data-w-topups><p class="hint">Loading top-up requests…</p></div>
        </section>
        <section class="card">
          <div class="ledger-filter-row">
            <h2>Wallet ledger</h2>
            <div class="filters" aria-label="Ledger direction">
              <button type="button" class="chip is-on" data-ledger-dir="all">All</button>
              <button type="button" class="chip" data-ledger-dir="CR">Credits (CR)</button>
              <button type="button" class="chip" data-ledger-dir="DR">Debits (DR)</button>
            </div>
          </div>
          <div data-w-ledger><p class="hint">Loading wallet ledger…</p></div>
        </section>
      </div>`;
  }

  function bulkBills() {
    return `
      <div class="screen bulk-bills">
        <header class="page-head page-head-row">
          <div>
            <p class="kicker">BBPS · Bulk</p>
            <h1>Bulk bills</h1>
            <p>Select one or more billers, set how many bills each, download the sheet, fill only account details, then upload.</p>
          </div>
          <div class="page-head-actions">
            <button type="button" class="btn subtle" data-bulk-template disabled>Download sheet</button>
            <label class="btn yellow" data-bulk-upload-label>
              Upload file
              <input type="file" data-bulk-file accept=".csv,.xlsx,.xlsm,text/csv" hidden />
            </label>
          </div>
        </header>
        <p class="preview-result bulk-status" data-bulk-status role="status" hidden></p>
        <section class="card bulk-biller-card">
          <div class="panel-head-inline">
            <h2>1. Choose billers &amp; counts</h2>
            <p class="hint" data-bulk-biller-picked>No billers selected yet.</p>
          </div>
          <div class="bulk-biller-toolbar">
            <label class="field">
              Category
              <select data-bulk-category aria-label="BBPS category">
                <option value="">Loading categories…</option>
              </select>
            </label>
            <label class="field bulk-biller-search">
              Search biller
              <input type="search" data-bulk-biller-q placeholder="Name or id" aria-label="Search billers" />
            </label>
          </div>
          <div class="bulk-biller-list" data-bulk-biller-list role="listbox" aria-label="Billers" aria-multiselectable="true">
            <p class="hint">Pick a category, then tap billers to add them.</p>
          </div>
          <div class="bulk-selected" data-bulk-selected hidden>
            <h3>Selected for sheet</h3>
            <div data-bulk-selected-rows></div>
            <p class="hint" data-bulk-selected-total>0 rows will be in the download.</p>
          </div>
        </section>
        <section class="stats" aria-label="Batch summary">
          <article class="stat"><span>Rows</span><strong data-bulk-stat-rows>0</strong><em data-bulk-stat-file>—</em></article>
          <article class="stat"><span>Fetch OK</span><strong data-bulk-stat-fetch>0</strong><em data-bulk-stat-fetch-fail>0 failed</em></article>
          <article class="stat"><span>Due total</span><strong data-bulk-stat-due>₹0.00</strong><em data-bulk-stat-wallet>Wallet —</em></article>
          <article class="stat"><span>Paid</span><strong data-bulk-stat-paid>0</strong><em data-bulk-stat-status>—</em></article>
        </section>
        <section class="card">
          <div class="panel-head-inline">
            <h2>2. Batch work surface</h2>
            <div class="filters" aria-label="Due date filter">
              <button type="button" class="chip is-on" data-bulk-due="all">All</button>
              <button type="button" class="chip" data-bulk-due="overdue">Overdue</button>
              <button type="button" class="chip" data-bulk-due="today">Due today</button>
              <button type="button" class="chip" data-bulk-due="upcoming">Upcoming</button>
              <button type="button" class="chip" data-bulk-due="none">No due date</button>
            </div>
          </div>
          <div class="transaction-toolbar">
            <div class="filters" aria-label="Fetch filter">
              <button type="button" class="chip is-on" data-bulk-fetch="all">All fetch</button>
              <button type="button" class="chip" data-bulk-fetch="ok">OK</button>
              <button type="button" class="chip" data-bulk-fetch="failed">Failed</button>
              <button type="button" class="chip" data-bulk-fetch="pending">Pending</button>
            </div>
            <label class="transaction-search"><span class="mi" aria-hidden="true">search</span><input data-bulk-q type="search" placeholder="Search account, ref" aria-label="Search bulk rows" /></label>
          </div>
          <p class="hint" data-bulk-empty>Select billers and counts, download the sheet, fill consumer numbers, then upload.</p>
          <div class="table-wrap" data-bulk-table hidden></div>
          <div class="bulk-actions" data-bulk-actions hidden>
            <button type="button" class="btn subtle" data-bulk-refetch>Re-fetch failed</button>
            <button type="button" class="btn subtle" data-bulk-export>Export CSV</button>
            <button type="button" class="btn subtle" data-bulk-cancel>Cancel batch</button>
            <label class="field bulk-pin-field">Wallet PIN<input data-bulk-pin type="password" inputmode="numeric" maxlength="6" autocomplete="off" /></label>
            <button type="button" class="btn yellow" data-bulk-proceed>Proceed &amp; pay ready</button>
          </div>
        </section>
        <section class="card">
          <div class="panel-head-inline"><h2>Recent batches</h2><button type="button" class="btn subtle" data-bulk-refresh>Refresh</button></div>
          <div data-bulk-batches><p class="hint">Loading…</p></div>
        </section>
      </div>`;
  }

  function transactions() {
    return `
      <div class="screen transaction-book">
        <header class="transaction-head">
          <div><p class="kicker">Transaction book</p><h1>Live transactions</h1><p>All recorded BBPS payments, PG orders, and vouchers for this retailer account.</p></div>
          <div class="transaction-head-actions">
            <!-- Stage-2 / txn status: Bharat Connect top-right — not B Assured -->
            <img class="txn-bc-logo" src="assets/bbps/bharat-connect-logo.svg" alt="Bharat Connect" />
            <button class="btn subtle" type="button" data-txn-refresh>Refresh</button>
          </div>
        </header>
        <section class="transaction-summary" aria-label="Transaction summary">
          <article><span class="mi">receipt_long</span><div><small>Total records</small><strong data-txn-total>0</strong><p>Matching current filter</p></div></article>
          <article><span class="mi">payments</span><div><small>Successful value</small><strong data-txn-value>₹0.00</strong><p>Settled transactions</p></div></article>
          <article><span class="mi">pending_actions</span><div><small>Pending sync</small><strong data-txn-pending>0</strong><p>Sync live status below</p></div></article>
        </section>
        <section class="txn-status-card">
          <div class="txn-status-copy">
            <h2><span class="mi" aria-hidden="true">manage_search</span> Check payment status</h2>
            <p>Look up any BBPS payment reference. Pending wallet holds settle or refund automatically.</p>
          </div>
          <div class="txn-status-form">
            <label class="field">Payment reference
              <input name="status_ref" data-bbps-status-ref placeholder="e.g. T1A21264B6569A2F4E6F120D" autocomplete="off" />
            </label>
            <button class="btn yellow" type="button" data-bbps-lookup-status>Check status</button>
            <p class="bbps-lookup-box txn-lookup-box" data-bbps-lookup-result role="status" hidden></p>
          </div>
        </section>
        <section class="transaction-ledger">
          <div class="transaction-toolbar">
            <div class="txn-filter-group">
              <div class="txn-view-tabs" aria-label="Transaction type">
                <button type="button" class="is-on" data-txn-service="all">All</button>
                <button type="button" data-txn-service="bbps">BBPS</button>
                <button type="button" data-txn-service="vouchers">Vouchers</button>
                <button type="button" data-txn-service="pg">PG Orders</button>
              </div>
              <div class="filters" aria-label="Status filter" data-txn-state-bar>
                <button type="button" class="chip is-on" data-txn-state="all">All status</button>
                <button type="button" class="chip" data-txn-state="success">Success</button>
                <button type="button" class="chip" data-txn-state="pending">Pending</button>
                <button type="button" class="chip" data-txn-state="failed">Failed</button>
              </div>
            </div>
            <label class="transaction-search"><span class="mi" aria-hidden="true">search</span><input data-txn-q type="search" placeholder="Search transaction or BBPS reference" aria-label="Search transactions" /></label>
          </div>
          <div class="txn-feedback" data-txn-feedback role="status" hidden></div>
          <div class="transaction-sheet">
            <div class="transaction-columns" data-txn-columns aria-hidden="true"><span></span><span>Service &amp; reference</span><span>Consumer / Channel</span><span>Time</span><span>Amount</span><span>Status</span></div>
            <div class="transaction-rows" data-txn-rows><p class="hint">Loading transactions…</p></div>
          </div>
          <div class="receipt txn-receipt-drawer" data-txn-receipt hidden aria-hidden="true"></div>
        </section>
      </div>`;
  }

  function profile() {
    return `
      <div class="screen">
        <header class="page-head">
          <div>
            <p class="kicker">Account &amp; security</p>
            <h1>Retailer profile &amp; KYC</h1>
          </div>
          <p>View your verified onboarding checks, manage outlet profile, Wallet PIN, password, and active sessions.</p>
        </header>
        <div class="stats">
          <article class="stat"><span>Account ID</span><strong data-p-id>—</strong><em data-p-email>—</em></article>
          <article class="stat"><span>KYC status</span><strong data-p-kyc>Checking…</strong><em data-p-checks>—</em></article>
          <article class="stat"><span>Allowed payment modes</span><strong data-p-rails>—</strong><em data-p-services>—</em></article>
          <article class="stat"><span>MTD commission</span><strong data-p-comm>₹0.00</strong><em data-p-tds>TDS ₹0.00</em></article>
        </div>
        <div class="split">
          <form class="card fields" data-profile-form>
            <h2>Outlet &amp; business profile</h2>
            <label class="field">Contact / Display name<input name="display_name" maxlength="80" placeholder="Your full name" /></label>
            <label class="field">Outlet / Shop name<input name="outlet_name" maxlength="80" placeholder="Store or agency name" /></label>
            <div class="fields two">
              <label class="field">City<input name="city" maxlength="64" placeholder="City" /></label>
              <label class="field">GSTIN (optional)<input name="gstin" maxlength="15" autocapitalize="characters" placeholder="15-char GSTIN" /></label>
            </div>
            <label class="field">Business address<input name="address" maxlength="200" placeholder="Shop / office address" /></label>
            <button class="btn yellow" type="submit">Save profile</button>
            <p class="preview-result" data-p-save-status role="status" hidden></p>
          </form>
          <div class="fields">
            <form class="card fields" data-pin-form>
              <h2>Wallet transaction PIN</h2>
              <p class="hint" data-pin-hint>Set a 4 to 6 digit Wallet PIN required before wallet payments.</p>
              <label class="field" data-pin-current-wrap hidden>Current Wallet PIN<input name="current_pin" type="password" inputmode="numeric" maxlength="6" autocomplete="off" /></label>
              <label class="field">New Wallet PIN (4-6 digits)<input name="new_pin" type="password" inputmode="numeric" minlength="4" maxlength="6" required autocomplete="new-password" /></label>
              <button class="btn yellow" type="submit">Save Wallet PIN</button>
              <p class="preview-result" data-pin-status role="status" hidden></p>
            </form>
            <form class="card fields" data-password-form>
              <h2>Change account password</h2>
              <label class="field">Current password<input name="current_password" type="password" required autocomplete="current-password" /></label>
              <label class="field">New password (12+ chars)<input name="new_password" type="password" minlength="12" maxlength="128" required autocomplete="new-password" /></label>
              <button class="btn" type="submit">Update password</button>
              <p class="preview-result" data-pw-status role="status" hidden></p>
            </form>
          </div>
        </div>
        <section class="card">
          <div class="panel-head-inline">
            <h2>Commission &amp; GST invoices</h2>
            <span class="hint" data-p-comm-month></span>
          </div>
          <p class="hint" data-p-tds-rule>TDS is decided on each commission credit. PAN missing uses 206AA. An approved certificate uses 197 for this account only.</p>
          <div data-p-invoices><p class="hint">Loading commission…</p></div>
        </section>
        <section class="card">
          <h2>Lower deduction certificate</h2>
          <p class="hint" data-p-cert-status>Loading certificate status…</p>
          <form class="fields" data-tds-cert-form>
            <label class="field">Certificate number<input name="certificate_no" maxlength="40" autocapitalize="characters" required /></label>
            <div class="fields two">
              <label class="field">TDS %<input name="rate_percent" type="number" min="0" max="100" step="0.01" required /></label>
              <label class="field">Valid from<input name="valid_from" type="date" required /></label>
            </div>
            <label class="field">Valid to<input name="valid_to" type="date" required /></label>
            <button class="btn yellow" type="submit">Submit for approval</button>
            <p class="preview-result" data-p-cert-result role="status" hidden></p>
          </form>
        </section>
        <section class="card">
          <div class="panel-head-inline">
            <h2>Active sessions</h2>
            <button class="btn subtle" type="button" data-revoke-sessions>Sign out other devices</button>
          </div>
          <div data-p-sessions><p class="hint">Loading sessions…</p></div>
        </section>
      </div>`;
  }

  function unavailable(label) {
    return `
      <div class="screen">
        <header class="page-head">
          <div><p class="kicker">Service access</p><h1>${esc(label)}</h1></div>
        </header>
        <section class="card">
          <h2>Service not enabled</h2>
          <p>This service is not assigned to your retailer account or is not yet connected. Contact your administrator to enable it.</p>
          <a class="btn yellow" href="#home">Back to Home</a>
        </section>
      </div>`;
  }

  function aeps() { return unavailable("AEPS Cash Withdrawal"); }
  function dmt() { return unavailable("Domestic Money Transfer (DMT)"); }
  function recharge() { return unavailable("Mobile & DTH Recharges"); }
  function vouchers() {
    return `
      <div class="screen">
        <header class="page-head">
          <div><p class="kicker">Vouchers</p><h1>Brand vouchers</h1></div>
          <p>Issue a voucher order through your assigned retailer account.</p>
        </header>
        <form class="card fields" data-voucher-form>
          <label class="field">Brand<input name="brand" required placeholder="Brand name" autocomplete="off" /></label>
          <label class="field">Amount (₹)<input name="amount" inputmode="decimal" required placeholder="100.00" /></label>
          <button class="btn yellow" type="submit">Create voucher order</button>
          <p class="preview-result" data-voucher-status role="status" hidden></p>
        </form>
      </div>`;
  }
  function support() {
    return `
      <div class="screen">
        <header class="page-head">
          <div><p class="kicker">Support</p><h1>Retailer helpdesk</h1></div>
          <p>For pending BBPS payments, use Transactions → Sync status or check reference status on Bill Pay.</p>
        </header>
        <section class="card">
          <h2>Quick resolution</h2>
          <p>Wallet holds for failed BBPS transactions are released back to your available balance automatically. For manual float UTR inquiries, check the status under Wallet → Top-up requests.</p>
          <div class="support-actions">
            <a class="btn yellow" href="#transactions">Open transactions</a>
            <a class="btn" href="#wallet">Open wallet</a>
          </div>
        </section>
      </div>`;
  }

  const screens = { home, aeps, dmt, recharge, bills, "bulk-bills": bulkBills, vouchers, wallet, transactions, profile, support };
  const titles = {
    home: "Home",
    aeps: "AEPS",
    dmt: "DMT",
    recharge: "Recharges",
    bills: "Bill pay",
    "bulk-bills": "Bulk bills",
    vouchers: "Vouchers",
    wallet: "Float and Ledger",
    transactions: "Transactions",
    profile: "Profile & KYC",
    support: "Support",
  };

  window.Payswap = {
    screens,
    titles,
    esc,
    rupee,
    mount(root, name, allowedServices, entitlements) {
      const viewToService = {
        bills: "bbps",
        "bulk-bills": "bbps_bulk",
        wallet: "wallet",
        transactions: "transactions",
        profile: "profile",
        support: "support",
        recharge: "recharge",
        vouchers: "vouchers",
        dmt: "dmt",
        aeps: "aeps",
      };
      const key = screens[name] ? name : "home";
      const svc = viewToService[key];
      if (svc === "bbps_bulk") {
        const bulkOn = Boolean(entitlements && entitlements.bbps_bulk_enabled);
        const bbpsOn = Array.isArray(allowedServices) && allowedServices.includes("bbps");
        if (!bulkOn || !bbpsOn) {
          root.innerHTML = unavailable(titles[key] || "Bulk bills");
          return key;
        }
      } else if (svc && Array.isArray(allowedServices) && !allowedServices.includes(svc)) {
        root.innerHTML = unavailable(titles[key] || svc);
        return key;
      }
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
