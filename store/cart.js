(function () {
  "use strict";
  const store = window.MiniPCBStore;
  const list = document.getElementById("cart-items");
  if (!list) return;
  const { element, formatMoney } = store;
  function render() {
    const items = store.readCart();
    list.replaceChildren();
    document.getElementById("empty-cart").hidden = Boolean(items.length);
    document.getElementById("cart-content").hidden = !items.length;
    let subtotal = 0;
    let unavailable = false;
    const currency = items.length ? store.product(items[0].sku).currency : "USD";
    for (const item of items) {
      const product = store.product(item.sku);
      const available = store.available(product) && product.currency === currency;
      unavailable ||= !available;
      if (available) subtotal += product.priceCents * item.quantity;
      const row = element("li", undefined, "cart-item");
      const details = element("div");
      const link = element("a", product.name);
      link.href = product.productPage;
      const heading = element("h2");
      heading.append(link);
      details.append(heading, element("p", `Rev ${product.revision} · ${item.sku}`, "store-meta"), element("p", available ? `${formatMoney(product.priceCents, currency)} each` : "Not available for purchase", available ? "" : "is-error"));
      const controls = element("div", undefined, "cart-controls");
      const label = element("label", "Quantity");
      label.htmlFor = `cart-quantity-${item.sku}`;
      const input = element("input");
      Object.assign(input, { id: label.htmlFor, type: "number", min: "1", max: "99", step: "1", value: String(item.quantity), required: true });
      input.addEventListener("change", () => {
        try {
          store.update(item.sku, Number(input.value));
          document.getElementById(input.id)?.focus();
          store.message("Cart quantity updated.");
        } catch (error) { input.value = String(item.quantity); store.message(error.message, true); }
      });
      const remove = element("button", "Remove", "store-button secondary");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove ${product.name} from cart`);
      remove.addEventListener("click", () => {
        try { store.remove(item.sku); store.message(`${product.name} removed.`); document.getElementById("cart-title").focus(); }
        catch (error) { store.message(error.message, true); }
      });
      controls.append(label, input, remove);
      row.append(details, controls, element("p", available ? formatMoney(product.priceCents * item.quantity, currency) : "Unavailable", "cart-line-total"));
      list.append(row);
    }
    document.getElementById("cart-subtotal").textContent = unavailable ? "Unavailable" : formatMoney(subtotal, currency);
    document.getElementById("cart-unavailable").hidden = !unavailable;
    const button = document.getElementById("checkout-start");
    button.disabled = !items.length || unavailable;
    window.dispatchEvent(new CustomEvent("minipcb:cart-rendered"));
  }
  document.getElementById("clear-cart").addEventListener("click", () => {
    try { store.clear(); store.message("Your cart has been cleared."); document.getElementById("cart-title").focus(); }
    catch (error) { store.message(error.message, true); }
  });
  window.addEventListener("minipcb:cartchange", render);
  render();
})();
