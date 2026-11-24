/* ParkPe dashboard shell for apps/parkpe/dashboard/index.html.

   Vehicle slides and menus. Screen HTML comes from apps/parkpe/js/screens.js
   (window.ParkpeScreens). Does not call apps/backend, and must not load
   apps/payswap/js/session.js.
*/
const slides = [
  {
    reg: "DL 01 AB 1234",
    subtitle: "Hyundai Creta | Polar White",
    insurance: { text: "12 Mar 2027", alert: false },
    puc: { text: "Exp: 18 days", alert: true, label: "PUC expires in 18 days" },
    fitness: { text: "4 Jan 2028", alert: false },
    rc: { text: "Verified", alert: false },
  },
  {
    reg: "HR 26 DK 9081",
    subtitle: "Maruti Suzuki Swift | Magma Grey",
    insurance: { text: "Expired", alert: true, label: "Insurance has expired" },
    puc: { text: "22 Aug 2026", alert: false },
    fitness: { text: "—", alert: false },
    rc: { text: "Verified", alert: false },
  },
];

const services = {
  "bill-payments": {
    title: "Bill Payments",
    icon: "receipt_long",
    blurb: "Pay electricity, water, gas, broadband and other bills from one list.",
  },
  "parkpe-voucher": {
    title: "ParkPe Voucher",
    icon: "redeem",
    blurb: "Buy, link and check the balance of ParkPe vouchers.",
  },
  "brand-vouchers": {
    title: "Brand Voucher",
    icon: "local_activity",
    blurb: "Browse brand vouchers and keep the ones you use most within reach.",
  },
  "qr-scan": {
    title: "Connect QR",
    icon: "qr_code_scanner",
    blurb: "Scan a ParkPe or merchant QR to pay for parking and other services.",
  },
  fastag: {
    title: "FASTag",
    icon: "local_shipping",
    blurb: "Check FASTag balance and recharge the tag on your vehicle.",
  },
  "pay-challan": {
    title: "Pay challan",
    icon: "request_quote",
    blurb: "Look up a traffic challan and pay it without leaving ParkPe.",
  },
  carpool: {
    title: "CoPilot",
    icon: "hail",
    blurb: "Find or offer a shared ride on your usual route.",
  },
  transactions: {
    title: "Transaction History",
    icon: "history",
    blurb: "Every parking, FASTag, challan and bill payment in one timeline.",
  },
  connect: {
    title: "ParkPe Connect",
    icon: "qr_code_2",
    blurb: "Vehicles, QR stickers and the documents that keep them on the road.",
  },
  parking: {
    title: "Parking desk",
    icon: "local_parking",
    blurb: "Find a bay, book it, and see the sessions already on your vehicles.",
  },
  support: {
    title: "Support",
    icon: "support_agent",
    blurb: "Help centre, FAQs and a way to reach ParkPe when something is stuck.",
  },
  "account-settings": {
    title: "Settings",
    icon: "settings",
    blurb: "Password, alerts and the preferences for this account.",
  },
  profile: {
    title: "Profile",
    icon: "person",
    blurb: "The name, mobile number and vehicles tied to this ParkPe account.",
  },
  notifications: {
    title: "Notifications",
    icon: "notifications",
    blurb: "PUC, insurance, FASTag and parking alerts collected in one place.",
  },
};

const shell = document.querySelector(".shell");
const backdrop = document.querySelector(".sidebar-backdrop");
const menuBtn = document.querySelector(".menu-btn");
const voucherToggle = document.querySelector(".voucher-toggle");
const voucherSub = document.querySelector(".voucher-sub");
const profileBtn = document.querySelector(".profile-btn");
const profileMenu = document.querySelector(".profile-menu");
const notifyBtn = document.querySelector(".notify-btn");
const notifyMenu = document.querySelector(".notify-menu");
const notifyList = document.querySelector(".notify-list");
const notifyBadge = document.querySelector(".badge");
const markRead = document.querySelector(".mark-read");
const slideRoot = document.querySelector(".hero-slide");
const slideCount = document.querySelector(".slide-count");
const hero = document.querySelector(".hero");
const dashboardView = document.querySelector("#view-dashboard");
const serviceView = document.querySelector("#view-service");
const greeting = document.querySelector("#greeting");
const welcomeSummary = document.querySelector("#welcome-summary");
const crumb = document.querySelector("#crumb");
const searchInput = document.querySelector("#site-search");
const searchResults = document.querySelector("#search-results");
const searchToggle = document.querySelector(".search-toggle");
const toast = document.querySelector("#toast");

let slideIndex = 0;
let slideTimer = 0;
let slideBusy = false;
let pausedUntil = 0;
let toastTimer = 0;
let unread = [];
let searchHits = [];
let searchCursor = -1;

const catalog = uniqueCatalog([
  ...document.querySelectorAll(".nav-link, .quick-action, .pill-btn"),
]);

function linkName(node) {
  const named = node.querySelector(".nav-label");
  const source = named ? named.cloneNode(true) : node.cloneNode(true);
  source.querySelectorAll(".mi").forEach((icon) => icon.remove());
  return source.textContent.replace(/\s+/g, " ").trim();
}

function uniqueCatalog(nodes) {
  const seen = new Set();
  const items = [];
  nodes.forEach((node) => {
    const name = linkName(node);
    const href = node.getAttribute("href") || "";
    const key = `${href}|${name}`;
    if (!name || seen.has(key)) return;
    seen.add(key);
    items.push({ name, href, group: node.classList.contains("nav-link") ? "Menu" : "Shortcut" });
  });
  slides.forEach((slide, index) => {
    items.push({
      name: slide.reg,
      href: "#dashboard",
      group: "Vehicle",
      slide: index,
    });
  });
  return items;
}

function hourGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function alertItems() {
  const items = [];
  slides.forEach((slide, index) => {
    ["insurance", "puc", "fitness", "rc"].forEach((key) => {
      const cell = slide[key];
      if (cell.alert) items.push({ index, reg: slide.reg, label: cell.label || cell.text });
    });
  });
  return items;
}

function reminderItems() {
  const vehicleReminders = alertItems().map((item) => ({
    title: item.label,
    body: item.reg,
    type: "Reminder",
    view: "dashboard",
    slide: item.index,
  }));
  return [
    ...vehicleReminders,
    {
      title: "FASTag balance low",
      body: "HR 26 DK 9081 balance is below ₹200.",
      type: "Reminder",
      view: "fastag",
    },
  ];
}

function renderSummary() {
  greeting.textContent = hourGreeting();
  const due = document.querySelectorAll(".table-row.is-due").length;
  const parts = [`${slides.length} vehicle${slides.length === 1 ? "" : "s"}`];
  if (due) parts.push(`${due} parking session due`);
  welcomeSummary.textContent = parts.join(" · ");
}

function renderNotifications() {
  notifyList.replaceChildren();
  if (!unread.length) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "You're all caught up.";
    notifyList.append(empty);
    notifyBadge.hidden = true;
    markRead.hidden = true;
    return;
  }
  notifyBadge.hidden = false;
  notifyBadge.textContent = String(unread.length);
  markRead.hidden = false;
  unread.forEach((item, index) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "notify-item";
    const title = document.createElement("strong");
    title.textContent = item.title;
    const body = document.createElement("p");
    body.textContent = item.body;
    const type = document.createElement("small");
    type.textContent = item.type;
    row.append(title, body, type);
    row.addEventListener("click", () => {
      unread.splice(index, 1);
      renderNotifications();
      openTarget(item.view, item.slide);
    });
    notifyList.append(row);
  });
}

function renderSlide(index) {
  const slide = slides[index];
  slideRoot.querySelector("h2").textContent = slide.reg;
  slideRoot.querySelector(".hero-sub").textContent = slide.subtitle;
  slideCount.textContent = `${index + 1} / ${slides.length}`;
  slideRoot.querySelectorAll(".stat").forEach((card) => {
    const value = slide[card.dataset.key];
    card.classList.toggle("is-alert", value.alert);
    card.querySelector("strong").textContent = value.text;
  });
}

function goToSlide(next) {
  if (slideBusy || slides.length < 2) return;
  slideBusy = true;
  slideRoot.classList.add("is-leaving");
  window.setTimeout(() => {
    slideIndex = (next + slides.length) % slides.length;
    renderSlide(slideIndex);
    slideRoot.classList.remove("is-leaving");
    slideBusy = false;
  }, 280);
}

function jumpToSlide(index) {
  slideIndex = index;
  slideBusy = false;
  slideRoot.classList.remove("is-leaving");
  renderSlide(index);
  pauseBriefly();
  hero.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function restartAutoplay() {
  window.clearInterval(slideTimer);
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;
  slideTimer = window.setInterval(() => {
    if (document.hidden || Date.now() < pausedUntil || hero.matches(":hover")) return;
    goToSlide(slideIndex + 1);
  }, 5000);
}

function pauseBriefly() {
  pausedUntil = Date.now() + 8000;
  restartAutoplay();
}

function closeMenus() {
  profileMenu.classList.remove("is-open");
  notifyMenu.classList.remove("is-open");
  profileBtn.setAttribute("aria-expanded", "false");
  notifyBtn.setAttribute("aria-expanded", "false");
}

function setSidebar(open) {
  shell.classList.toggle("sidebar-open", open);
  menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
}

function setSearchOpen(open) {
  shell.classList.toggle("search-open", open);
  searchToggle.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) searchInput.focus();
}

function hideSearchResults() {
  searchResults.hidden = true;
  searchInput.setAttribute("aria-expanded", "false");
  searchHits = [];
  searchCursor = -1;
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, 4200);
}

function renderSearch(query) {
  const q = query.trim().toLowerCase();
  searchResults.replaceChildren();
  if (!q) {
    hideSearchResults();
    return;
  }
  searchHits = catalog.filter((item) => item.name.toLowerCase().includes(q)).slice(0, 6);
  searchCursor = searchHits.length ? 0 : -1;
  searchResults.hidden = false;
  searchInput.setAttribute("aria-expanded", "true");
  if (!searchHits.length) {
    const empty = document.createElement("p");
    empty.className = "search-empty";
    empty.textContent = "No matching service or vehicle.";
    searchResults.append(empty);
    return;
  }
  searchHits.forEach((hit, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "search-hit";
    button.setAttribute("role", "option");
    if (index === searchCursor) button.classList.add("is-active");
    button.append(hit.name);
    const meta = document.createElement("small");
    meta.textContent = hit.group;
    button.append(meta);
    button.addEventListener("click", () => chooseSearchHit(hit));
    searchResults.append(button);
  });
}

function chooseSearchHit(hit) {
  searchInput.value = "";
  hideSearchResults();
  setSearchOpen(false);
  const view = (hit.href || "#dashboard").replace("#", "") || "dashboard";
  openTarget(view, hit.slide);
}

function showView(name) {
  const service = services[name];
  const isDashboard = name === "dashboard" || !service;
  dashboardView.hidden = !isDashboard;
  serviceView.hidden = isDashboard;
  const title = isDashboard ? "Dashboard" : service.title;
  crumb.textContent = title;
  document.title = `${title} · ParkPe`;
  if (!isDashboard) {
    window.ParkpeScreens.mount(serviceView, name);
  }
  document.querySelectorAll(".nav-link").forEach((link) => {
    const active = link.dataset.view === (isDashboard ? "dashboard" : name);
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const voucherOpen = name === "parkpe-voucher" || name === "brand-vouchers";
  voucherSub.classList.toggle("is-open", voucherOpen);
  voucherToggle.setAttribute("aria-expanded", voucherOpen ? "true" : "false");
  if (window.innerWidth < 1024) setSidebar(false);
  closeMenus();
}

function openTarget(view, slide) {
  const next = `#${view}`;
  if ((location.hash || "#dashboard") !== next) location.hash = view;
  else showView(view);
  if (view === "dashboard" && Number.isInteger(slide)) jumpToSlide(slide);
}

function routeFromHash() {
  const name = (location.hash || "#dashboard").replace(/^#/, "") || "dashboard";
  showView(name);
}

document.querySelector(".shell").addEventListener("click", (event) => {
  const link = event.target.closest("a[href^='#']");
  if (!link) return;
  const name = link.getAttribute("href").slice(1) || "dashboard";
  if (name === "dashboard" || services[name]) showView(name);
});

menuBtn.addEventListener("click", () => {
  setSidebar(!shell.classList.contains("sidebar-open"));
  setSearchOpen(false);
});

backdrop.addEventListener("click", () => setSidebar(false));

voucherToggle.addEventListener("click", () => {
  const open = voucherToggle.getAttribute("aria-expanded") !== "true";
  voucherToggle.setAttribute("aria-expanded", open ? "true" : "false");
  voucherSub.classList.toggle("is-open", open);
});

notifyBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  const open = !notifyMenu.classList.contains("is-open");
  closeMenus();
  notifyMenu.classList.toggle("is-open", open);
  notifyBtn.setAttribute("aria-expanded", open ? "true" : "false");
});

profileBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  const open = !profileMenu.classList.contains("is-open");
  closeMenus();
  profileMenu.classList.toggle("is-open", open);
  profileBtn.setAttribute("aria-expanded", open ? "true" : "false");
});

searchToggle.addEventListener("click", (event) => {
  event.stopPropagation();
  setSearchOpen(!shell.classList.contains("search-open"));
});

searchInput.addEventListener("input", () => renderSearch(searchInput.value));

searchInput.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    if (!searchHits.length) return;
    event.preventDefault();
    searchCursor =
      event.key === "ArrowDown"
        ? (searchCursor + 1) % searchHits.length
        : (searchCursor - 1 + searchHits.length) % searchHits.length;
    searchResults.querySelectorAll(".search-hit").forEach((hit, index) => {
      hit.classList.toggle("is-active", index === searchCursor);
    });
  }
  if (event.key === "Enter" && searchHits[searchCursor]) {
    event.preventDefault();
    chooseSearchHit(searchHits[searchCursor]);
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".menu-wrap")) closeMenus();
  if (!event.target.closest(".search") && !event.target.closest(".search-toggle")) {
    hideSearchResults();
  }
});

document.addEventListener("parkpe-toast", (event) => showToast(event.detail));

document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    setSearchOpen(true);
    searchInput.focus();
    searchInput.select();
  }
  if (event.key === "Escape") {
    closeMenus();
    setSidebar(false);
    hideSearchResults();
    setSearchOpen(false);
  }
});

markRead.addEventListener("click", () => {
  unread = [];
  renderNotifications();
});

document.querySelectorAll(".js-logout").forEach((button) => {
  button.addEventListener("click", () => {
    closeMenus();
    showToast("Logout will work once sign-in is connected. This preview stays open.");
  });
});

document.querySelector(".carousel-prev").addEventListener("click", () => {
  pauseBriefly();
  goToSlide(slideIndex - 1);
});

document.querySelector(".carousel-next").addEventListener("click", () => {
  pauseBriefly();
  goToSlide(slideIndex + 1);
});

hero.addEventListener("pointerdown", pauseBriefly);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) window.clearInterval(slideTimer);
  else restartAutoplay();
});

window.addEventListener("hashchange", routeFromHash);

unread = reminderItems();
renderSummary();
renderSlide(0);
renderNotifications();
restartAutoplay();
routeFromHash();
