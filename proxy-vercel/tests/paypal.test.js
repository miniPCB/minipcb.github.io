// No dependencies or network access. Run: node proxy-vercel/tests/paypal.test.js
const assert = require("node:assert/strict");
const path = require("node:path");
const tests = [];
const test = (name, run) => tests.push({ name, run });
const origin = "https://minipcb.com";
const orderId = "5O190127TN364715T";
const captureId = "3C679366HH908993F";
let helper, create, capture, webhook, calls, responses, logs;
const originalEnv = { ...process.env };
const originalFetch = global.fetch;
const originalError = console.error;

function setup() {
  for (const name of Object.keys(process.env)) if (/^(PAYPAL_|STORE_|RESEND_|REQUEST_)/.test(name)) delete process.env[name];
  Object.assign(process.env, { PAYPAL_CLIENT_ID: "test-client", PAYPAL_CLIENT_SECRET: "test-only-secret", PAYPAL_ENVIRONMENT: "sandbox", PAYPAL_WEBHOOK_ID: "test-webhook", RESEND_API_KEY: "test-email-key", REQUEST_TO_EMAIL: "orders@example.com", REQUEST_FROM_EMAIL: "store@example.com" });
  for (const name of ["_paypal", "paypal-create-order", "paypal-capture-order", "paypal-webhook"]) delete require.cache[require.resolve(path.join("../api", name))];
  helper = require("../api/_paypal");
  create = require("../api/paypal-create-order");
  capture = require("../api/paypal-capture-order");
  webhook = require("../api/paypal-webhook");
  calls = []; responses = []; logs = [];
  console.error = (...args) => logs.push(args);
  global.fetch = async (url, options) => {
    calls.push({ url, ...options });
    const next = responses.shift();
    assert.ok(next, `Unexpected external request: ${url}`);
    if (next.error) throw new Error("simulated connection failure");
    return { ok: (next.status || 200) < 400, status: next.status || 200, json: async () => next.body };
  };
}
async function invoke(handler, body, overrides = {}) {
  const req = { method: "POST", headers: { origin, "content-type": "application/json" }, body, ...overrides };
  const res = { headers: {}, code: 200, setHeader(name, value) { this.headers[name] = value; }, status(code) { this.code = code; return this; }, json(value) { this.body = value; return this; }, end() { return this; } };
  await handler(req, res);
  assert.equal(responses.length, 0, "Expected external requests were not made");
  return res;
}
function activate() { Object.assign(helper.STORE_PRODUCTS["04A-006-KIT"], { active: true, priceCents: 1250 }); }
function fixture(status = "APPROVED", captureStatus) {
  activate();
  const summary = helper.calculateOrder([{ sku: "04A-006-KIT", quantity: 2 }]);
  const order = { ...helper.createOrderBody(summary), id: orderId, status, create_time: "2026-10-04T12:00:00Z", payer: { name: { given_name: "Test", surname: "Buyer" }, email_address: "buyer@example.com" } };
  order.purchase_units[0].shipping = { name: { full_name: "Test Buyer" }, address: { address_line_1: "123 Test St", admin_area_2: "Test City", postal_code: "12345", country_code: "US" } };
  if (captureStatus) order.purchase_units[0].payments = { captures: [{ id: captureId, status: captureStatus, amount: { currency_code: "USD", value: "25.00" }, create_time: "2026-10-04T12:01:00Z" }] };
  return order;
}
const oauth = () => responses.push({ body: { access_token: "test-token" } });
const response = body => responses.push({ body });
const items = (quantity = 2, sku = "04A-006-KIT") => ({ items: [{ sku, quantity }] });
const sigHeaders = { "content-type": "application/json", "paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://api.paypal.com/test-cert", "paypal-transmission-id": "test-transmission", "paypal-transmission-sig": "test-signature", "paypal-transmission-time": "2026-10-04T12:01:00Z" };
const event = () => ({ event_type: "PAYMENT.CAPTURE.COMPLETED", resource: { id: captureId, supplementary_data: { related_ids: { order_id: orderId } } } });

test("shipped catalogs cannot accept payments", async () => {
  for (const sku of Object.keys(helper.STORE_PRODUCTS)) {
    const res = await invoke(create, items(1, sku));
    assert.equal(res.code, 400);
  }
  assert.equal(calls.length, 0);
});
test("unknown and prototype SKUs are rejected", async () => {
  for (const sku of ["unknown", "toString", "__proto__"]) assert.equal((await invoke(create, items(1, sku))).code, 400);
});
test("active zero-price products remain unpurchasable", async () => {
  helper.STORE_PRODUCTS["04A-006-KIT"].active = true;
  assert.equal((await invoke(create, items())).code, 400);
  assert.equal(calls.length, 0);
});
test("quantity must be an integer between 1 and 99", async () => {
  activate();
  for (const count of [0, -1, 100, 1.5, "2", null]) assert.equal((await invoke(create, items(count))).code, 400);
  assert.equal(helper.calculateOrder(items(99).items).items[0].quantity, 99);
});
test("empty, duplicate, malformed and oversized requests fail closed", async () => {
  activate();
  for (const body of [{}, { items: [] }, { items: [items().items[0], items().items[0]] }, "bad-json", "x".repeat(17000)]) assert.equal((await invoke(create, body)).code, 400);
  assert.equal((await invoke(create, items(), { headers: { origin, "content-type": "text/plain" } })).code, 415);
});
test("browser origins and preflights are checked", async () => {
  for (const handler of [create, capture]) {
    for (const badOrigin of ["https://evil.example", "null", ""]) assert.equal((await invoke(handler, {}, { headers: { origin: badOrigin }, method: "OPTIONS" })).code, 403);
    const res = await invoke(handler, {}, { method: "OPTIONS" });
    assert.equal(res.code, 204);
    assert.equal(res.headers["Access-Control-Allow-Origin"], origin);
  }
  process.env.STORE_ALLOWED_ORIGINS = "https://custom.example";
  assert.equal((await invoke(create, items())).code, 403);
});
test("public configuration contains no secrets and defaults to sandbox", async () => {
  delete process.env.PAYPAL_ENVIRONMENT;
  const res = await invoke(create, undefined, { method: "GET" });
  assert.equal(res.body.environment, "sandbox");
  assert.equal(res.body.checkoutEnabled, false);
  assert.equal(res.body.clientId, "test-client");
  assert.ok(!JSON.stringify(res.body).includes("test-only-secret"));
  assert.ok(!JSON.stringify(res.body).includes("test-email-key"));
});
test("invalid environment, currency, and shipping configuration fail closed", async () => {
  for (const [key, value] of [["PAYPAL_ENVIRONMENT", "production"], ["STORE_CURRENCY", "JPY"], ["STORE_SHIPPING_FLAT_CENTS", "-1"], ["STORE_SHIPPING_FLAT_CENTS", "1.5"]]) {
    const previous = process.env[key]; process.env[key] = value;
    assert.equal((await invoke(create, undefined, { method: "GET" })).code, 503);
    if (previous === undefined) delete process.env[key]; else process.env[key] = previous;
  }
});
test("server pricing and shipping override all browser money fields", async () => {
  activate(); process.env.STORE_SHIPPING_FLAT_CENTS = "450";
  oauth(); response({ id: orderId });
  const body = items(); body.items[0].priceCents = 1; body.shipping = 0; body.total = 1; body.tax = 100;
  const res = await invoke(create, body);
  assert.equal(res.code, 200);
  const sent = JSON.parse(calls[1].body).purchase_units[0];
  assert.equal(sent.amount.value, "29.50");
  assert.equal(sent.amount.breakdown.item_total.value, "25.00");
  assert.equal(sent.amount.breakdown.shipping.value, "4.50");
  assert.equal(sent.items[0].unit_amount.value, "12.50");
  assert.ok(sent.custom_id.startsWith("minipcb-v1:"));
  assert.ok(calls.every(call => call.url.startsWith("https://api-m.sandbox.paypal.com/")));
  assert.ok(calls[1].headers["PayPal-Request-Id"]);
});
test("explicit live selects only the live API", async () => {
  process.env.PAYPAL_ENVIRONMENT = "live";
  assert.equal(helper.settings().apiBase, "https://api-m.paypal.com");
});
test("OAuth failure and order-create failure are sanitized", async () => {
  activate(); responses.push({ status: 401, body: { secret: "never expose this" } });
  assert.equal((await invoke(create, items())).code, 502);
  oauth(); responses.push({ status: 500, body: { secret: "never expose this" } });
  const res = await invoke(create, items());
  assert.equal(res.code, 502);
  assert.ok(!JSON.stringify([res.body, logs]).includes("never expose this"));
});
test("invalid capture IDs never reach PayPal", async () => {
  for (const id of [null, "", "../secret", "x".repeat(200), "<script>"]) assert.equal((await invoke(capture, { paypalOrderId: id })).code, 400);
  assert.equal(calls.length, 0);
});
test("orders not signed by this store cannot be captured", async () => {
  const order = fixture(); order.purchase_units[0].custom_id = "some-other-store";
  oauth(); response(order);
  assert.equal((await invoke(capture, { paypalOrderId: orderId })).code, 409);
  assert.equal(calls.length, 2);
});
test("tampered prices and extra discounts cannot be captured", async () => {
  for (const tamper of [order => { order.purchase_units[0].items[0].unit_amount.value = "0.01"; }, order => { order.purchase_units[0].amount.breakdown.discount = { currency_code: "USD", value: "1.00" }; }]) {
    const order = fixture(); tamper(order); oauth(); response(order);
    assert.equal((await invoke(capture, { paypalOrderId: orderId })).code, 409);
  }
});
test("price changes and deactivation stop uncaptured orders", async () => {
  const order = fixture(); helper.STORE_PRODUCTS["04A-006-KIT"].priceCents += 1;
  oauth(); response(order);
  assert.equal((await invoke(capture, { paypalOrderId: orderId })).code, 409);
  helper.STORE_PRODUCTS["04A-006-KIT"].active = false;
  oauth(); response(order);
  assert.equal((await invoke(capture, { paypalOrderId: orderId })).code, 400);
});
test("capture success returns a minimal paid receipt and sends complete email", async () => {
  const before = fixture(); const paid = structuredCloneFixture(before, "COMPLETED");
  oauth(); response(before); response(paid); response(paid); response({ id: "email-test-id" });
  const res = await invoke(capture, { paypalOrderId: orderId });
  assert.equal(res.body.status, "COMPLETED");
  assert.equal(res.body.totalCents, 2500);
  assert.equal(res.body.paypalOrderId, orderId);
  assert.ok(!JSON.stringify(res.body).includes("buyer@example.com"));
  assert.equal(calls[2].headers["PayPal-Request-Id"], `minipcb-capture-${orderId}`);
  const email = JSON.parse(calls[4].body);
  for (const value of [orderId, captureId, "Test Buyer", "buyer@example.com", "123 Test St", "04A-006-KIT", "25.00", "USD", "2026-10-04T12:01:00Z"]) assert.ok(email.text.includes(value), value);
  assert.ok(calls[4].headers["Idempotency-Key"].includes(captureId));
});
function structuredCloneFixture(before, status) {
  const order = JSON.parse(JSON.stringify(before)); order.status = "COMPLETED";
  order.purchase_units[0].payments = { captures: [{ id: captureId, status, amount: { currency_code: "USD", value: "25.00" }, create_time: "2026-10-04T12:01:00Z" }] };
  return order;
}
test("successful capture stays successful if Resend fails", async () => {
  const before = fixture(); const paid = structuredCloneFixture(before, "COMPLETED");
  oauth(); response(before); response(paid); response(paid); responses.push({ status: 500, body: {} });
  const res = await invoke(capture, { paypalOrderId: orderId });
  assert.equal(res.code, 200); assert.equal(res.body.status, "COMPLETED");
  assert.ok(logs.some(log => log[0] === "store_order_email_failed"));
});
test("missing email configuration does not fail a paid purchase", async () => {
  delete process.env.RESEND_API_KEY;
  const paid = fixture("COMPLETED", "COMPLETED"); oauth(); response(paid); response(paid);
  assert.equal((await invoke(capture, { paypalOrderId: orderId })).body.status, "COMPLETED");
});
test("duplicate captures are read, not recaptured; notices are deduplicated", async () => {
  const paid = fixture("COMPLETED", "COMPLETED");
  helper.STORE_PRODUCTS["04A-006-KIT"].active = false;
  oauth(); response(paid); response(paid); response({ id: "email-test-id" });
  assert.equal((await invoke(capture, { paypalOrderId: orderId })).body.status, "COMPLETED");
  oauth(); response(paid); response(paid);
  assert.equal((await invoke(capture, { paypalOrderId: orderId })).body.status, "COMPLETED");
  assert.equal(calls.filter(call => call.url.endsWith("/capture")).length, 0);
  assert.equal(calls.filter(call => call.url.includes("resend.com")).length, 1);
});
test("lost capture response reconciles with PayPal before returning", async () => {
  const before = fixture(); const paid = structuredCloneFixture(before, "COMPLETED");
  oauth(); response(before); responses.push({ error: true }); response(paid); response(paid); response({ id: "email-test-id" });
  assert.equal((await invoke(capture, { paypalOrderId: orderId })).body.status, "COMPLETED");
});
test("capture failure is not reported as paid", async () => {
  const before = fixture(); oauth(); response(before); responses.push({ status: 422, body: {} }); response(before);
  assert.equal((await invoke(capture, { paypalOrderId: orderId })).code, 502);
});
test("pending and declined captures are not paid or captured again", async () => {
  for (const [paypalStatus, expected] of [["PENDING", "PENDING"], ["DECLINED", "NOT_COMPLETED"]]) {
    oauth(); response(fixture("COMPLETED", paypalStatus));
    assert.equal((await invoke(capture, { paypalOrderId: orderId })).body.status, expected);
  }
  assert.equal(calls.filter(call => call.url.endsWith("/capture")).length, 0);
});
test("webhooks without configuration, headers or verified signatures fail closed", async () => {
  assert.equal((await invoke(webhook, event(), { headers: { "content-type": "application/json" } })).code, 400);
  oauth(); response({ verification_status: "FAILURE" });
  assert.equal((await invoke(webhook, event(), { headers: sigHeaders })).code, 403);
  delete process.env.PAYPAL_WEBHOOK_ID;
  assert.equal((await invoke(webhook, event(), { headers: sigHeaders })).code, 503);
});
test("verified completed webhook retrieves trusted order and notifies", async () => {
  const paid = fixture("COMPLETED", "COMPLETED");
  oauth(); response({ verification_status: "SUCCESS" }); response(paid); response({ id: "email-test-id" });
  assert.equal((await invoke(webhook, event(), { headers: sigHeaders })).code, 200);
  const verifyBody = JSON.parse(calls[1].body);
  assert.equal(verifyBody.webhook_id, "test-webhook"); assert.deepEqual(verifyBody.webhook_event, event());
});
test("webhook retries email failures without trusting payload amounts", async () => {
  const paid = fixture("COMPLETED", "COMPLETED");
  oauth(); response({ verification_status: "SUCCESS" }); response(paid); responses.push({ status: 500, body: {} });
  assert.equal((await invoke(webhook, event(), { headers: sigHeaders })).code, 502);
});
test("verified irrelevant events are acknowledged and ignored", async () => {
  oauth(); response({ verification_status: "SUCCESS" });
  assert.equal((await invoke(webhook, { event_type: "CUSTOMER.DISPUTE.CREATED" }, { headers: sigHeaders })).body.ignored, true);
});

(async () => {
  let failed = 0;
  for (const { name, run } of tests) {
    setup();
    try { await run(); console.log(`PASS ${name}`); }
    catch (error) { failed++; originalError(`FAIL ${name}`, error); }
  }
  process.env = originalEnv; global.fetch = originalFetch; console.error = originalError;
  console.log(`${tests.length - failed}/${tests.length} payment checks passed (mock PayPal/Resend; no payments sent).`);
  process.exitCode = failed ? 1 : 0;
})();
