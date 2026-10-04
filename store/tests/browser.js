/* Local browser regression checks. No third-party test dependencies. */
(async function () {
  "use strict";
  const result = document.getElementById("results");
  if (!["localhost", "127.0.0.1"].includes(location.hostname)) {
    result.textContent = "Run these checks from a local development server.";
    result.dataset.status = "disabled";
    return;
  }
  const frame = document.getElementById("store");
  const lines = [];
  let checks = 0;
  function check(condition, description) { if (!condition) throw new Error(description); checks++; lines.push("PASS " + description); }
  function load(file) { return new Promise(resolve => { frame.onload = () => resolve(frame.contentWindow); frame.src = "/store/" + file; }); }
  const tick = () => new Promise(resolve => setTimeout(resolve, 50));
  const id = "5O190127TN364715T";
  const key = "minipcb_store_cart_v1";
  const pendingKey = "minipcb_store_pending_order_v1";
  const receiptKey = "minipcb_store_receipt_v1";
  function activate(win) { Object.assign(win.MINIPCB_PRODUCTS["04A-006-KIT"], { active: true, priceCents: 1250 }); win.dispatchEvent(new win.CustomEvent("minipcb:cartchange")); }
  function checkoutMock(win, options = {}) {
    let handlers;
    const requests = [];
    win.fetch = async (url, request) => {
      requests.push({ url, ...request });
      let body;
      if (!request.body) body = { ok: true, checkoutEnabled: true, clientId: "test-client", currency: "USD", environment: "sandbox", shippingFlatCents: 450 };
      else if (url.endsWith("paypal-create-order")) body = { ok: true, paypalOrderId: id };
      else if (options.networkFailure) throw new Error("simulated network failure");
      else body = { ok: true, status: options.pending ? "PENDING" : "COMPLETED", paypalOrderId: id };
      return { ok: true, json: async () => body };
    };
    win.paypal = { Buttons(callbacks) {
      handlers = callbacks;
      return { async render(node) { node.textContent = "Mock PayPal button"; }, async close() {} };
    } };
    const append = win.document.head.append.bind(win.document.head);
    win.document.head.append = node => {
      if (node.tagName === "SCRIPT" && node.src.startsWith("https://www.paypal.com/sdk/js")) { Promise.resolve().then(() => node.onload()); return; }
      append(node);
    };
    return { requests, callbacks: () => handlers };
  }
  try {
    localStorage.removeItem(key); localStorage.removeItem("tb26_api_base"); sessionStorage.removeItem(pendingKey); sessionStorage.removeItem(receiptKey);
    let win = await load("index.html");
    check(win.document.querySelectorAll(".store-card").length === 3, "three distinct product formats render");
    check([...win.document.querySelectorAll(".store-add-form button")].every(button => button.disabled), "all shipped products are disabled");
    try { win.MiniPCBStore.add("04A-006-KIT", 1); throw new Error("Inactive product accepted"); } catch (error) { check(error.message.includes("not available"), "inactive product rejected by cart logic"); }
    check(win.document.documentElement.scrollWidth <= frame.clientWidth, "store fits a 390px mobile viewport");
    check(win.document.querySelector(".store-feature img").naturalWidth > 0, "product image loads");
    check(win.document.querySelector('a[href="../04A/04A-006.html"]'), "technical documentation link is present");
    check(win.MiniPCBStore.resolveApiBase() === "https://minipcb-github-io.vercel.app/api", "default API base matches the existing site");
    localStorage.setItem("tb26_api_base", "http://localhost:5500/api/");
    check(win.MiniPCBStore.resolveApiBase() === "http://localhost:5500/api", "existing stored API override is reused");
    win = await load("index.html?apiBase=http%3A%2F%2Flocalhost%3A4173%2Fapi");
    check(win.MiniPCBStore.resolveApiBase() === "http://localhost:4173/api", "query override takes precedence");
    check(win.document.querySelector('a[data-store-link][href*="cart.html"]').href.includes("apiBase="), "API override follows store navigation");
    localStorage.removeItem("tb26_api_base");
    activate(win);
    const form = win.document.querySelector('[id="04A-006-KIT"] form');
    form.querySelector("input").disabled = false; form.querySelector("input").value = "2"; form.querySelector("button").disabled = false;
    form.querySelector("button").click();
    check(win.document.querySelector("[data-cart-count]").textContent === "2", "Add to Cart updates the navigation count");
    check(JSON.stringify(JSON.parse(localStorage.getItem(key))) === JSON.stringify([{ sku: "04A-006-KIT", quantity: 2 }]), "cart storage contains only SKU and quantity");
    win = await load("cart.html");
    check(win.MiniPCBStore.readCart()[0].quantity === 2, "cart survives page navigation and reload");
    check(win.document.getElementById("checkout-start").disabled, "stale inactive cart cannot check out");
    activate(win);
    check(win.document.getElementById("cart-subtotal").textContent.includes("25.00"), "active fixture subtotal is correct");
    let input = win.document.querySelector('input[type="number"]'); input.value = "3"; input.dispatchEvent(new win.Event("change"));
    check(win.MiniPCBStore.readCart()[0].quantity === 3, "quantity control updates persisted cart");
    input = win.document.querySelector('input[type="number"]'); input.value = "100"; input.dispatchEvent(new win.Event("change"));
    check(win.MiniPCBStore.readCart()[0].quantity === 3, "quantity above 99 is rejected");
    check(win.document.getElementById("store-status").textContent.includes("99"), "invalid quantity has a clear error");
    win.document.querySelector('button[aria-label^="Remove"]').click();
    check(!localStorage.getItem(key) && !win.document.getElementById("empty-cart").hidden, "remove item shows empty-cart state");
    win.MiniPCBStore.add("04A-006-KIT", 2); win.document.getElementById("clear-cart").click();
    check(win.MiniPCBStore.readCart().length === 0, "clear cart removes all entries");
    win.MiniPCBStore.add("04A-006-KIT", 2);
    const mock = checkoutMock(win);
    win.document.getElementById("checkout-start").click(); await tick();
    check(mock.callbacks(), "PayPal controls load after explicit checkout request");
    check(win.document.getElementById("checkout-total").textContent.includes("29.50"), "shipping is included in checkout estimate");
    check(win.document.getElementById("checkout-status").textContent.includes("Sandbox"), "sandbox checkout is clearly identified");
    await mock.callbacks().createOrder();
    check(JSON.parse(mock.requests[1].body).items[0].quantity === 2 && Object.keys(JSON.parse(mock.requests[1].body)).length === 1, "checkout sends only cart items");
    const cancelLoaded = new Promise(resolve => { frame.onload = () => resolve(frame.contentWindow); });
    mock.callbacks().onCancel(); win = await cancelLoaded;
    check(win.location.pathname.endsWith("cancel.html") && win.MiniPCBStore.readCart().length === 1, "PayPal cancellation preserves the cart");
    check(win.document.querySelector('a[href$="cart.html"]'), "cancel page returns to cart");
    win = await load("cart.html"); activate(win);
    const failed = checkoutMock(win, { networkFailure: true });
    win.document.getElementById("checkout-start").click(); await tick();
    await failed.callbacks().createOrder(); await failed.callbacks().onApprove({ orderID: id });
    check(!win.document.getElementById("checkout-retry").hidden && win.MiniPCBStore.readCart().length === 1, "uncertain capture preserves cart and offers status recovery");
    check(JSON.parse(sessionStorage.getItem(pendingKey)).paypalOrderId === id, "pending order survives refresh");
    win = await load("cart.html");
    check(win.document.getElementById("cart-editor").disabled && !win.document.getElementById("checkout-retry").hidden, "refresh restores pending payment recovery without a new checkout");
    checkoutMock(win);
    const successLoaded = new Promise(resolve => { frame.onload = () => resolve(frame.contentWindow); });
    win.document.getElementById("checkout-retry").click(); win = await successLoaded;
    check(win.location.pathname.endsWith("success.html"), "confirmed capture redirects to success");
    check(win.document.getElementById("payment-title").textContent === "Payment received", "success page shows confirmed payment");
    check(win.document.getElementById("payment-order").textContent.includes(id), "success page shows only the order reference");
    check(!localStorage.getItem(key) && !sessionStorage.getItem(pendingKey), "confirmed capture clears the cart and pending order");
    sessionStorage.removeItem(receiptKey);
    win = await load("success.html?orderId=" + id);
    check(win.document.getElementById("payment-title").textContent !== "Payment received", "a query parameter alone cannot claim payment success");
    result.dataset.status = "passed";
    result.textContent = lines.join("\n") + `\n${checks} browser checks passed. Mock payments only.`;
  } catch (error) {
    result.dataset.status = "failed";
    result.textContent = lines.join("\n") + "\nFAIL " + error.message + "\n" + error.stack;
  } finally {
    localStorage.removeItem(key); localStorage.removeItem("tb26_api_base"); sessionStorage.removeItem(pendingKey); sessionStorage.removeItem(receiptKey);
  }
})();
