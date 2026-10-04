# miniPCB Store

Plain HTML, CSS, and JavaScript served by the existing GitHub Pages site. All payment and notification operations run in `proxy-vercel/`. See [backend setup and Sandbox checklist](../proxy-vercel/README.md#minipcb-store--paypal) before activating products.

- `index.html` / `products.js`: 04A-006 Rev A1-01 Bare PCB, Kit, and 2-Up Educational Panel. All ship inactive at zero price. The existing component-layout image is used because the proposed `04A-006_board_top_01.png` is not in the repository.
- `store.js`: shared cart operations, navigation count, money formatting, product rendering, and existing `apiBase` / `tb26_api_base` API resolution.
- `cart.html` / `cart.js`: quantities (1–99), removal, clear cart, subtotal, and empty/unavailable states. `localStorage.minipcb_store_cart_v1` stores only `{sku, quantity}` entries.
- `checkout.js`: obtains public configuration from Vercel, loads the official PayPal SDK on demand, and calls server create/capture endpoints. Unresolved capture IDs and minimal confirmed receipts use session storage to support recovery; neither is trusted by the server.
- `success.html` / `cancel.html`: confirmed receipt or preserved-cart cancellation. A URL order ID alone cannot claim successful payment.
- `store.css`: scoped additions using colors and navigation from `../styles.css`. All pages retain the site's Google Analytics measurement ID.
- `tests/browser.html`: local-only browser regression harness with mocked payments. Start it with `node store/tests/serve.js` and open the printed URL. Use a separate browser profile: the harness resets store cart/session keys on its local origin.

Navigation is duplicated across the existing static pages. This change adds Store to the homepage and 04A-006 navigation, plus a small purchasing link above that board's technical tabs. It does not regenerate unrelated pages or modify the unused navigation template. Store pages link back to Home, About, Contact, and the technical page.

No prices were found in the existing product documentation. Update both the backend authoritative catalog and the frontend display catalog with approved prices and availability. The backend always recomputes amounts; editing browser storage or JavaScript cannot set a checkout price. Secrets belong exclusively in Vercel environment variables.

The initial shipping rule is one flat amount per order, defaulting to zero. There is no inventory or tax engine. See the backend README for activation, fulfillment, email retry limits, and the deliberate switch from Sandbox to live.
