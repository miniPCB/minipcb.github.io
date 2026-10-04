(function () {
  "use strict";
  const store = window.MiniPCBStore;
  const start = document.getElementById("checkout-start");
  const PENDING_KEY = "minipcb_store_pending_order_v1";
  const RECEIPT_KEY = "minipcb_store_receipt_v1";
  const validId = value => typeof value === "string" && /^[A-Z0-9]{17}$/.test(value);
  const status = (text, error = false) => store.message(text, error, "checkout-status");

  if (!start) {
    if (document.getElementById("payment-title")) {
      let receipt;
      try { receipt = JSON.parse(sessionStorage.getItem(RECEIPT_KEY)); } catch (_) { /* No locally confirmed receipt. */ }
      const id = new URLSearchParams(location.search).get("orderId");
      if (validId(id) && receipt?.paypalOrderId === id && receipt.status === "COMPLETED") {
        document.getElementById("payment-title").textContent = "Payment received";
        document.getElementById("payment-message").textContent = "Thank you for supporting miniPCB.";
        document.getElementById("payment-order").textContent = `PayPal order ID: ${id}`;
      } else {
        document.getElementById("payment-title").textContent = "Payment confirmation";
        document.getElementById("payment-message").textContent = "There is no payment confirmation in this browser session. Check your PayPal receipt for payment status.";
        if (validId(id)) document.getElementById("payment-order").textContent = `PayPal order ID: ${id}`;
      }
    }
    return;
  }

  const panel = document.getElementById("checkout-panel");
  const buttons = document.getElementById("paypal-buttons");
  const retry = document.getElementById("checkout-retry");
  let paypalButtons;
  let cartSnapshot;
  let pendingOrderId = "";
  let busy = false;
  let approving = false;
  let generation = 0;
  let sdkPromise;

  function lock(value) {
    store.setLocked(value);
    document.getElementById("cart-editor").disabled = value;
  }
  function savePending(id) {
    // Persist before capture so a lost response never requires starting another payment.
    sessionStorage.setItem(PENDING_KEY, JSON.stringify({ paypalOrderId: id, apiBase: store.resolveApiBase() }));
    pendingOrderId = id;
  }
  function loadSdk(clientId, currency) {
    if (sdkPromise) return sdkPromise;
    sdkPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      const url = new URL("https://www.paypal.com/sdk/js");
      url.search = new URLSearchParams({ "client-id": clientId, currency, intent: "capture", components: "buttons", "disable-funding": "paylater,credit" });
      script.src = url.href;
      script.async = true;
      const timer = setTimeout(() => { script.remove(); reject(new Error("PayPal took too long to load. Reload this page to try again.")); }, 20000);
      script.onload = () => { clearTimeout(timer); window.paypal?.Buttons ? resolve() : reject(new Error("PayPal could not be loaded. Please reload the page.")); };
      script.onerror = () => { clearTimeout(timer); reject(new Error("PayPal could not be loaded. Please check your connection and reload.")); };
      document.head.append(script);
    });
    return sdkPromise;
  }

  async function capture(id) {
    if (busy) return;
    busy = true;
    retry.hidden = true;
    buttons.hidden = true;
    lock(true);
    status("Confirming your payment with PayPal…");
    try {
      savePending(id);
      const result = await store.api("/paypal-capture-order", { paypalOrderId: id });
      if (result.status === "NOT_COMPLETED") {
        sessionStorage.removeItem(PENDING_KEY);
        pendingOrderId = "";
        approving = false;
        lock(false);
        status("PayPal reports that this payment was not completed. Your cart is preserved. Contact miniPCB if you need help.", true);
        start.disabled = false;
        return;
      }
      if (result.status !== "COMPLETED") {
        status("PayPal has not confirmed a completed payment yet. Use Check payment status before starting another checkout.");
        retry.hidden = false;
        return;
      }
      // The API result, never a query parameter, is the payment confirmation.
      let savedReceipt = false;
      try {
        sessionStorage.setItem(RECEIPT_KEY, JSON.stringify({ paypalOrderId: id, status: "COMPLETED" }));
        sessionStorage.removeItem(PENDING_KEY);
        savedReceipt = true;
      } catch (_) { /* Storage failure cannot undo a confirmed payment. */ }
      pendingOrderId = "";
      approving = false;
      lock(false);
      try { store.clear(); } catch (_) { /* Payment succeeded even if storage becomes unavailable. */ }
      if (!savedReceipt) {
        panel.hidden = false;
        status(`Payment received. Thank you for supporting miniPCB. PayPal order ID: ${id}`);
        start.disabled = true;
        return;
      }
      const url = store.pageUrl("success.html");
      url.searchParams.set("orderId", id);
      location.assign(url.href);
    } catch (_) {
      status(`We could not confirm payment status. Check this order before paying again: ${id}. You can retry confirmation or contact miniPCB.`, true);
      retry.hidden = false;
    } finally { busy = false; }
  }
  retry.addEventListener("click", () => { if (pendingOrderId) capture(pendingOrderId); });

  async function beginCheckout() {
    const items = store.readCart();
    if (pendingOrderId) return capture(pendingOrderId);
    if (!items.length || items.some(item => !store.available(store.product(item.sku)))) return;
    const thisGeneration = ++generation;
    start.disabled = true;
    panel.hidden = false;
    status("Loading secure checkout…");
    try {
      // Verify storage before handing control to PayPal.
      sessionStorage.setItem("minipcb_store_storage_check", "1");
      sessionStorage.removeItem("minipcb_store_storage_check");
      const config = await store.api("/paypal-create-order");
      if (!config.checkoutEnabled || !config.clientId) throw new Error("Checkout is not available yet. Please check back later.");
      if (items.some(item => store.product(item.sku).currency !== config.currency)) throw new Error("Product currency has changed. Please reload the store before checking out.");
      await loadSdk(config.clientId, config.currency);
      if (thisGeneration !== generation) return;
      cartSnapshot = JSON.stringify(items);
      const subtotal = items.reduce((sum, item) => sum + store.product(item.sku).priceCents * item.quantity, 0);
      document.getElementById("checkout-shipping").textContent = store.formatMoney(config.shippingFlatCents, config.currency);
      document.getElementById("checkout-total").textContent = store.formatMoney(subtotal + config.shippingFlatCents, config.currency);
      buttons.hidden = false;
      buttons.replaceChildren();
      paypalButtons = window.paypal.Buttons({
        style: { layout: "vertical", shape: "rect", label: "paypal", tagline: false },
        async createOrder() {
          if (JSON.stringify(store.readCart()) !== cartSnapshot) throw new Error("Your cart changed. Review it before checking out.");
          approving = true;
          lock(true);
          try {
            const created = await store.api("/paypal-create-order", { items: JSON.parse(cartSnapshot) });
            if (!validId(created.paypalOrderId)) throw new Error("PayPal did not return a valid order.");
            return created.paypalOrderId;
          } catch (error) { approving = false; lock(false); status(error.message, true); throw error; }
        },
        async onApprove(data) {
          if (!validId(data.orderID)) { status("PayPal did not return a valid order ID.", true); return; }
          await capture(data.orderID);
        },
        onCancel() {
          if (pendingOrderId) return;
          approving = false;
          lock(false);
          location.assign(store.pageUrl("cancel.html").href);
        },
        onError() {
          if (pendingOrderId) { status("Payment status is unconfirmed. Check payment status before paying again.", true); retry.hidden = false; return; }
          approving = false;
          lock(false);
          status("Checkout could not continue. Your cart is preserved. Please reload and try again.", true);
          start.disabled = false;
        }
      });
      await paypalButtons.render(buttons);
      status(config.environment === "sandbox" ? "Sandbox checkout: test payments only. Review the final total and shipping address in PayPal." : "Review the final total and shipping address in PayPal before approving payment.");
    } catch (error) { status(error.message || "Checkout is unavailable. Please try again.", true); start.disabled = false; }
  }
  start.addEventListener("click", beginCheckout);
  window.addEventListener("minipcb:cartchange", () => {
    if (pendingOrderId || approving) { lock(true); return; }
    generation++;
    if (paypalButtons) { paypalButtons.close().catch(() => {}); paypalButtons = null; }
    panel.hidden = true;
  });
  try {
    const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY));
    if (validId(pending?.paypalOrderId) && pending.apiBase === store.resolveApiBase()) {
      pendingOrderId = pending.paypalOrderId;
      panel.hidden = false;
      lock(true);
      retry.hidden = false;
      status(`Check payment status for order ${pendingOrderId} before starting another checkout.`);
    }
  } catch (_) { /* Checkout reports storage or configuration errors when requested. */ }
})();
