(function () {
  "use strict";
  const CART_KEY = "minipcb_store_cart_v1";
  const MAX_QUANTITY = 99;
  const products = window.MINIPCB_PRODUCTS;
  let locked = false;

  function product(sku) { return Object.prototype.hasOwnProperty.call(products, sku) ? products[sku] : null; }
  function available(item) { return Boolean(item && item.active && Number.isSafeInteger(item.priceCents) && item.priceCents > 0); }
  function quantity(value) { return Number.isInteger(value) && value >= 1 && value <= MAX_QUANTITY; }
  function readCart() {
    let parsed;
    try { parsed = JSON.parse(localStorage.getItem(CART_KEY) || "[]"); } catch (_) { return []; }
    if (!Array.isArray(parsed)) return [];
    const combined = new Map();
    for (const item of parsed.slice(0, 100)) {
      if (item && typeof item.sku === "string" && product(item.sku) && quantity(item.quantity)) combined.set(item.sku, Math.min(MAX_QUANTITY, (combined.get(item.sku) || 0) + item.quantity));
    }
    return [...combined].map(([sku, count]) => ({ sku, quantity: count }));
  }
  function writeCart(items) {
    if (locked) throw new Error("Finish or cancel the current checkout before changing the cart.");
    try {
      if (items.length) localStorage.setItem(CART_KEY, JSON.stringify(items.map(item => ({ sku: item.sku, quantity: item.quantity }))));
      else localStorage.removeItem(CART_KEY);
    } catch (_) { throw new Error("Your browser could not save the cart. Allow site storage and try again."); }
    window.dispatchEvent(new CustomEvent("minipcb:cartchange"));
  }
  function add(sku, count) {
    if (!available(product(sku))) throw new Error("This product is not available for purchase yet.");
    if (!quantity(count)) throw new Error(`Choose a whole number from 1 to ${MAX_QUANTITY}.`);
    const items = readCart();
    const existing = items.find(item => item.sku === sku);
    if (existing) {
      if (!quantity(existing.quantity + count)) throw new Error(`The cart can hold at most ${MAX_QUANTITY} of each product.`);
      existing.quantity += count;
    } else items.push({ sku, quantity: count });
    writeCart(items);
  }
  function update(sku, count) {
    if (!quantity(count)) throw new Error(`Choose a whole number from 1 to ${MAX_QUANTITY}.`);
    writeCart(readCart().map(item => item.sku === sku ? { sku, quantity: count } : item));
  }
  function remove(sku) { writeCart(readCart().filter(item => item.sku !== sku)); }
  function clear() { writeCart([]); }
  function formatMoney(cents, currency = "USD") { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(cents / 100); }

  function resolveApiBase() {
    const override = new URLSearchParams(location.search).get("apiBase")?.trim();
    let stored = "";
    try { stored = localStorage.getItem("tb26_api_base")?.trim(); } catch (_) { /* Storage may be unavailable. */ }
    const base = (override || stored || "https://minipcb-github-io.vercel.app/api").replace(/\/+$/, "");
    const url = new URL(base);
    if (url.username || url.password || url.search || url.hash || (url.protocol !== "https:" && !(url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)))) throw new Error("The API base must use HTTPS, or HTTP on localhost.");
    return base;
  }
  function pageUrl(file) {
    const url = new URL(file, location.href);
    const override = new URLSearchParams(location.search).get("apiBase");
    if (override) url.searchParams.set("apiBase", override);
    return url;
  }
  async function api(path, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 65000);
    try {
      const response = await fetch(resolveApiBase() + path, { method: body ? "POST" : "GET", headers: body ? { "Content-Type": "application/json" } : {}, ...(body ? { body: JSON.stringify(body) } : {}), signal: controller.signal, credentials: "omit" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) throw new Error(data.error || "The store could not complete this request. Please try again.");
      return data;
    } finally { clearTimeout(timer); }
  }
  function message(text, error = false, id = "store-status") {
    const element = document.getElementById(id);
    if (element) { element.textContent = text; element.classList.toggle("is-error", error); }
  }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function count() {
    const total = readCart().reduce((sum, item) => sum + item.quantity, 0);
    document.querySelectorAll("[data-cart-count]").forEach(node => { node.textContent = total; });
  }
  function renderProducts() {
    const list = document.getElementById("products");
    if (!list) return;
    for (const item of Object.values(products)) {
      const card = element("article", undefined, "store-card");
      card.id = item.sku;
      card.append(element("h3", item.format), element("p", `04A-006 · Rev ${item.revision}`, "store-meta"), element("p", item.description));
      card.append(element("p", available(item) ? formatMoney(item.priceCents, item.currency) : "Not yet available", "store-price"));
      const link = element("a", "Technical details");
      link.href = item.productPage;
      card.append(link);
      const form = element("form", undefined, "store-add-form");
      const label = element("label", "Quantity");
      label.htmlFor = `quantity-${item.sku}`;
      const input = element("input");
      Object.assign(input, { id: label.htmlFor, type: "number", min: "1", max: "99", step: "1", value: "1", required: true, disabled: !available(item) });
      const button = element("button", "Add to Cart", "store-button");
      button.type = "submit";
      button.disabled = !available(item);
      button.setAttribute("aria-label", `Add ${item.name} to cart`);
      form.append(label, input, button);
      form.addEventListener("submit", event => {
        event.preventDefault();
        try { add(item.sku, Number(input.value)); message(`${item.name} added to your cart.`); }
        catch (error) { message(error.message, true); }
      });
      card.append(form);
      list.append(card);
    }
  }

  window.MiniPCBStore = { CART_KEY, MAX_QUANTITY, product, available, readCart, add, update, remove, clear, formatMoney, resolveApiBase, pageUrl, api, message, element, setLocked(value) { locked = value; } };
  window.addEventListener("minipcb:cartchange", count);
  window.addEventListener("storage", event => { if (event.key === CART_KEY || event.key === null) window.dispatchEvent(new CustomEvent("minipcb:cartchange")); });
  document.querySelectorAll("[data-store-link]").forEach(link => { link.href = pageUrl(link.getAttribute("href")).href; });
  renderProducts();
  count();
})();
