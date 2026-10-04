const { createHmac, timingSafeEqual, randomUUID } = require("node:crypto");

// Authoritative prices. Activate only after prices and fulfillment are configured.
const STORE_PRODUCTS = {
  "04A-006-BARE": { sku: "04A-006-BARE", name: "04A-006 Bare PCB", revision: "A1-01", priceCents: 0, active: false },
  "04A-006-KIT": { sku: "04A-006-KIT", name: "04A-006 Kit", revision: "A1-01", priceCents: 0, active: false },
  "04A-006-2UP": { sku: "04A-006-2UP", name: "04A-006 2-Up Educational Panel", revision: "A1-01", priceCents: 0, active: false }
};
const MAX_QUANTITY = 99;
const MAX_CENTS = 99999999;
const DEFAULT_ORIGINS = [
  "https://minipcb.com", "https://www.minipcb.com", "https://minipcb.github.io",
  ...[3000, 4173, 5500].flatMap(port => [`http://localhost:${port}`, `http://127.0.0.1:${port}`])
];

class StoreError extends Error {
  constructor(status, message, code = "STORE_ERROR") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function settings(requireCredentials = true) {
  const environment = process.env.PAYPAL_ENVIRONMENT || "sandbox";
  if (!["sandbox", "live"].includes(environment)) throw new StoreError(503, "Store configuration is unavailable.");
  const currency = process.env.STORE_CURRENCY || "USD";
  // This cents-based store supports these two-decimal currencies only.
  if (!["USD", "CAD", "EUR", "GBP", "AUD", "NZD"].includes(currency)) throw new StoreError(503, "Store currency is not configured correctly.");
  const shippingValue = process.env.STORE_SHIPPING_FLAT_CENTS || "0";
  if (!/^\d+$/.test(shippingValue)) throw new StoreError(503, "Store shipping is not configured correctly.");
  const shippingFlatCents = Number(shippingValue);
  if (!Number.isSafeInteger(shippingFlatCents) || shippingFlatCents > MAX_CENTS) throw new StoreError(503, "Store shipping is not configured correctly.");
  const clientId = process.env.PAYPAL_CLIENT_ID;
  const clientSecret = process.env.PAYPAL_CLIENT_SECRET;
  if (requireCredentials && (!clientId || !clientSecret)) throw new StoreError(503, "Checkout is not available yet.");
  return {
    environment, currency, shippingFlatCents, clientId, clientSecret,
    apiBase: environment === "live" ? "https://api-m.paypal.com" : "https://api-m.sandbox.paypal.com"
  };
}

function browserRequest(req, res, methods = ["POST"]) {
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Vary", "Origin");
  const origin = String(req.headers.origin || "").replace(/\/+$/, "");
  const configured = process.env.STORE_ALLOWED_ORIGINS;
  const allowed = configured ? configured.split(",").map(s => s.trim().replace(/\/+$/, "")).filter(Boolean) : DEFAULT_ORIGINS;
  // Browser endpoints require an explicit allowed origin. Webhooks use signatures instead.
  if (!origin || !allowed.includes(origin)) {
    res.status(403).json({ ok: false, error: "Origin not allowed." });
    return false;
  }
  res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Access-Control-Allow-Methods", [...methods, "OPTIONS"].join(","));
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") { res.status(204).end(); return false; }
  if (!methods.includes(req.method)) {
    res.setHeader("Allow", [...methods, "OPTIONS"].join(", "));
    res.status(405).json({ ok: false, error: "Method not allowed." });
    return false;
  }
  return true;
}

function payload(req, maxBytes = 16384) {
  if (!/^application\/json(?:\s*;|$)/i.test(req.headers["content-type"] || "")) throw new StoreError(415, "Send an application/json request.");
  let body = req.body;
  try {
    if (Buffer.isBuffer(body)) body = body.toString("utf8");
    if (typeof body === "string") {
      if (Buffer.byteLength(body) > maxBytes) throw new Error();
      body = JSON.parse(body);
    }
    if (!body || typeof body !== "object" || Array.isArray(body) || Buffer.byteLength(JSON.stringify(body)) > maxBytes) throw new Error();
  } catch (_) { throw new StoreError(400, "Invalid request body."); }
  return body;
}

function validateOrderId(id) {
  if (typeof id !== "string" || !/^[A-Z0-9]{17}$/.test(id)) throw new StoreError(400, "Invalid PayPal order ID.");
  return id;
}

function calculateOrder(items) {
  if (!Array.isArray(items) || !items.length || items.length > Object.keys(STORE_PRODUCTS).length) throw new StoreError(400, "Choose at least one valid product.");
  const seen = new Set();
  const lines = items.map(item => {
    if (!item || typeof item.sku !== "string" || !Object.prototype.hasOwnProperty.call(STORE_PRODUCTS, item.sku)) throw new StoreError(400, "Unknown product.");
    if (seen.has(item.sku)) throw new StoreError(400, "Combine duplicate products into one cart entry.");
    seen.add(item.sku);
    if (!Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > MAX_QUANTITY) throw new StoreError(400, `Quantity must be a whole number from 1 to ${MAX_QUANTITY}.`);
    const product = STORE_PRODUCTS[item.sku];
    if (!product.active || !Number.isSafeInteger(product.priceCents) || product.priceCents <= 0 || product.priceCents > MAX_CENTS) throw new StoreError(400, `${product.name} is not available for purchase.`);
    return { sku: product.sku, name: `${product.name} (Rev ${product.revision})`, quantity: item.quantity, priceCents: product.priceCents };
  }).sort((a, b) => a.sku.localeCompare(b.sku));
  const { currency, shippingFlatCents } = settings(false);
  const subtotalCents = lines.reduce((sum, item) => sum + item.priceCents * item.quantity, 0);
  const totalCents = subtotalCents + shippingFlatCents;
  if (!Number.isSafeInteger(totalCents) || totalCents > MAX_CENTS) throw new StoreError(400, "Order exceeds the store limit.");
  return { items: lines, currency, subtotalCents, shippingCents: shippingFlatCents, totalCents };
}

function money(cents, currency) { return { currency_code: currency, value: (cents / 100).toFixed(2) }; }

function cents(amount, currency) {
  if (!amount || amount.currency_code !== currency || !/^\d{1,8}\.\d{2}$/.test(amount.value)) throw new StoreError(409, "Order amounts could not be verified.");
  const [whole, fraction] = amount.value.split(".");
  const value = Number(whole) * 100 + Number(fraction);
  if (value > MAX_CENTS) throw new StoreError(409, "Order exceeds the store limit.");
  return value;
}

function signature(order, referenceId) {
  const config = settings();
  // Sign a canonical price snapshot so another app's order cannot be captured here.
  const snapshot = [config.environment, referenceId, order.currency, order.shippingCents,
    order.items.map(item => [item.sku, item.name, item.quantity, item.priceCents])];
  return "minipcb-v1:" + createHmac("sha256", config.clientSecret).update(JSON.stringify(snapshot)).digest("hex");
}

function createOrderBody(order) {
  const referenceId = randomUUID();
  return {
    intent: "CAPTURE",
    purchase_units: [{
      reference_id: referenceId,
      custom_id: signature(order, referenceId),
      description: "miniPCB educational circuit boards",
      items: order.items.map(item => ({ sku: item.sku, name: item.name, quantity: String(item.quantity), category: "PHYSICAL_GOODS", unit_amount: money(item.priceCents, order.currency) })),
      amount: {
        ...money(order.totalCents, order.currency),
        breakdown: { item_total: money(order.subtotalCents, order.currency), shipping: money(order.shippingCents, order.currency) }
      }
    }],
    payment_source: { paypal: { experience_context: { brand_name: "miniPCB", shipping_preference: "GET_FROM_FILE", user_action: "PAY_NOW" } } }
  };
}

function verifyOrder(order) {
  if (order?.intent !== "CAPTURE" || order.purchase_units?.length !== 1) throw new StoreError(409, "This is not a miniPCB store order.");
  const unit = order.purchase_units[0];
  const currency = unit.amount?.currency_code;
  if (!Array.isArray(unit.items) || !unit.items.length || unit.items.length > 3) throw new StoreError(409, "Order items could not be verified.");
  const seen = new Set();
  const items = unit.items.map(item => {
    if (!Object.prototype.hasOwnProperty.call(STORE_PRODUCTS, item.sku) || seen.has(item.sku) || typeof item.name !== "string" || !/^[1-9]\d?$/.test(item.quantity)) throw new StoreError(409, "Order items could not be verified.");
    seen.add(item.sku);
    const priceCents = cents(item.unit_amount, currency);
    if (!priceCents) throw new StoreError(409, "Order price could not be verified.");
    return { sku: item.sku, name: item.name, quantity: Number(item.quantity), priceCents };
  }).sort((a, b) => a.sku.localeCompare(b.sku));
  const subtotalCents = items.reduce((sum, item) => sum + item.priceCents * item.quantity, 0);
  const breakdown = unit.amount?.breakdown;
  if (!breakdown || Object.keys(breakdown).some(key => !["item_total", "shipping"].includes(key))) throw new StoreError(409, "Order breakdown could not be verified.");
  const shippingCents = cents(breakdown.shipping, currency);
  const totalCents = cents(unit.amount, currency);
  if (cents(breakdown.item_total, currency) !== subtotalCents || totalCents !== subtotalCents + shippingCents) throw new StoreError(409, "Order totals could not be verified.");
  const snapshot = { items, currency, subtotalCents, shippingCents, totalCents };
  const expected = Buffer.from(signature(snapshot, unit.reference_id));
  const actual = Buffer.from(String(unit.custom_id || ""));
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) throw new StoreError(409, "This is not a verified miniPCB store order.");
  return snapshot;
}

async function fetchJson(url, options, service = "PayPal") {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new StoreError(502, `${service} is temporarily unavailable. Please try again.`, `${service.toUpperCase()}_ERROR`);
      error.upstreamStatus = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (error instanceof StoreError) throw error;
    throw new StoreError(502, `${service} could not be reached. Please try again.`, `${service.toUpperCase()}_ERROR`);
  } finally { clearTimeout(timer); }
}

async function accessToken() {
  const config = settings();
  const data = await fetchJson(`${config.apiBase}/v1/oauth2/token`, {
    method: "POST",
    headers: { Authorization: "Basic " + Buffer.from(`${config.clientId}:${config.clientSecret}`).toString("base64"), "Content-Type": "application/x-www-form-urlencoded" },
    body: "grant_type=client_credentials"
  });
  if (!data.access_token) throw new StoreError(502, "PayPal authentication is temporarily unavailable.");
  return data.access_token;
}

async function paypalRequest(path, { method = "GET", body, requestId, token } = {}) {
  const config = settings();
  const authorization = token || await accessToken();
  return fetchJson(config.apiBase + path, {
    method,
    headers: { Authorization: `Bearer ${authorization}`, "Content-Type": "application/json", Prefer: "return=representation", ...(requestId ? { "PayPal-Request-Id": requestId } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {})
  });
}

function completedCapture(order, snapshot) {
  const captures = order.purchase_units?.[0]?.payments?.captures || [];
  const capture = captures.find(item => item.status === "COMPLETED");
  if (!capture) return null;
  if (captures.length !== 1 || cents(capture.amount, snapshot.currency) !== snapshot.totalCents || !/^[A-Z0-9]{17}$/.test(capture.id)) throw new StoreError(409, "Captured amount needs review. Contact miniPCB before paying again.");
  return capture;
}

function normalizedOrder(order, snapshot, capture) {
  return { paypalOrderId: order.id, captureId: capture.id, status: "COMPLETED", currency: snapshot.currency, subtotalCents: snapshot.subtotalCents, shippingCents: snapshot.shippingCents, totalCents: snapshot.totalCents };
}

// A bounded warm-instance cache plus Resend's provider-side idempotency window.
// This is not a durable fulfillment ledger; see README before shipping orders.
const sentNotices = new Map();
async function sendOrderNotice(order, snapshot, capture) {
  if (sentNotices.has(capture.id)) return;
  const apiKey = process.env.RESEND_API_KEY;
  const to = process.env.STORE_ORDER_TO_EMAIL || process.env.REQUEST_TO_EMAIL;
  const from = process.env.STORE_ORDER_FROM_EMAIL || process.env.REQUEST_FROM_EMAIL;
  if (!apiKey || !to || !from) throw new StoreError(503, "Order email is not configured.", "RESEND_CONFIG");
  const shipping = order.purchase_units[0].shipping || {};
  const payer = order.payer || order.payment_source?.paypal || {};
  const customerName = shipping.name?.full_name || [payer.name?.given_name, payer.name?.surname].filter(Boolean).join(" ") || "(not supplied)";
  const address = shipping.address || {};
  const text = [
    "miniPCB order notice", `PayPal environment: ${settings().environment}`, "",
    `PayPal order ID: ${order.id}`, `PayPal capture ID: ${capture.id}`,
    `Customer: ${customerName}`, `Email: ${payer.email_address || "(not supplied)"}`,
    "Shipping address:", ...[address.address_line_1, address.address_line_2, address.admin_area_2, address.admin_area_1, address.postal_code, address.country_code].filter(Boolean),
    ...(!Object.keys(address).length ? ["(not supplied)"] : []), "", "Items:",
    ...snapshot.items.map(item => `${item.sku} | ${item.name} | quantity ${item.quantity} | unit ${money(item.priceCents, snapshot.currency).value} | item subtotal ${money(item.quantity * item.priceCents, snapshot.currency).value} ${snapshot.currency}`),
    "", `Subtotal: ${money(snapshot.subtotalCents, snapshot.currency).value}`,
    `Shipping: ${money(snapshot.shippingCents, snapshot.currency).value}`,
    `Total: ${money(snapshot.totalCents, snapshot.currency).value}`, `Currency: ${snapshot.currency}`,
    `Timestamp: ${capture.create_time || order.create_time || "(not supplied)"}`,
    "", "Confirm the capture in PayPal and check this capture ID against your fulfillment records before shipping."
  ].join("\n");
  await fetchJson("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json", "Idempotency-Key": `minipcb-order-${settings().environment}-${capture.id}` },
    body: JSON.stringify({ from, to: [to], subject: `miniPCB Order: ${order.id}`, text })
  }, "Resend");
  if (sentNotices.size >= 1000) sentNotices.delete(sentNotices.keys().next().value);
  sentNotices.set(capture.id, true);
}

function reportError(res, error, context) {
  // Never log provider bodies, customer details, credentials, or authorization headers.
  console.error(context, { code: error.code || "INTERNAL_ERROR", status: error.status || 500, upstreamStatus: error.upstreamStatus });
  return res.status(error instanceof StoreError ? error.status : 500).json({ ok: false, error: error instanceof StoreError ? error.message : "The store could not complete this request.", code: error.code || "INTERNAL_ERROR" });
}

module.exports = { STORE_PRODUCTS, StoreError, settings, browserRequest, payload, validateOrderId, calculateOrder, createOrderBody, verifyOrder, accessToken, paypalRequest, completedCapture, normalizedOrder, sendOrderNotice, reportError, randomUUID };
