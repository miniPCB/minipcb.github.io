# Vercel OpenAI Proxy (No Node Required)

## Deploy (dashboard, no CLI)

1) Create a new Vercel project and point it at this repo.
2) Set **Root Directory** to `proxy-vercel`.
3) Add Environment Variables:
   - `OPENAI_API_KEY` (required)
   - `PROXY_KEY` (optional; if set, clients must send `X-Proxy-Key`)
   - `RESEND_API_KEY` (required for part requests)
   - `REQUEST_TO_EMAIL` (required for part requests)
   - `REQUEST_FROM_EMAIL` (required for part requests; must be a verified sender)
   - `CONTACT_TO_EMAIL` (optional; defaults to `REQUEST_TO_EMAIL`)
   - `CONTACT_FROM_EMAIL` (optional; defaults to `REQUEST_FROM_EMAIL`; should be a verified sender)
   - `CONTACT_ALLOWED_ORIGINS` (optional; comma-separated list of allowed browser origins for the public contact form)
   - `CONTACT_RATE_MAX` (optional; default `5`)
   - `CONTACT_RATE_WINDOW_MS` (optional; default `900000`)
   - `DIGIKEY_CLIENT_ID` (required for DigiKey availability)
   - `DIGIKEY_CLIENT_SECRET` (required for DigiKey availability)
   - `DIGIKEY_SITE` (optional; default `US`)
   - `DIGIKEY_LANGUAGE` (optional; default `en`)
   - `DIGIKEY_CURRENCY` (optional; default `USD`)
   - `MOUSER_API_KEY` (required for Mouser availability)
   - `AVAILABILITY_CACHE_TTL_MS` (optional; default `300000`)
4) Deploy.

## Endpoints

- `GET /api/health`
- `GET /api/models`
- `POST /api/review`
- `POST /api/suggest`
- `POST /api/chat`
- `POST /api/create`
- `POST /api/part-request`
- `POST /api/contact`
- `POST /api/part-availability`

## Frontend Setup

In the Test Base 2026 Preferences:

```
API Base URL = https://<your-vercel-project>.vercel.app/api
Proxy Key     = <your PROXY_KEY>  (optional)
```

## Contact Form Notes

- `POST /api/contact` is intended for the public `contact.html` page, so it does not use `PROXY_KEY`.
- Protect it with `CONTACT_ALLOWED_ORIGINS` and keep the form hosted on your expected site origins.
- The endpoint falls back to `REQUEST_TO_EMAIL` and `REQUEST_FROM_EMAIL` if `CONTACT_TO_EMAIL` and `CONTACT_FROM_EMAIL` are not set.

## miniPCB Store / PayPal

The static storefront is in [`../store/`](../store/README.md). It uses the existing GitHub Pages site, this Vercel project, the official PayPal JavaScript SDK, and Resend. There is no ecommerce framework, database, build step, or new runtime dependency. Use a currently supported Vercel Node.js runtime with built-in `fetch` (Node.js 22 or newer). `vercel.json` allows up to 60 seconds for the three PayPal endpoints, including reconciliation and notification work.

All products ship with `priceCents: 0` and `active: false`. No live or sandbox purchase is possible until a valid product price and availability are explicitly configured. The environment defaults to **sandbox**; unknown environment values fail closed.

### Environment variables

Set real credentials only in Vercel Project Settings → Environment Variables. Scope sandbox and live credentials to the appropriate deployment environments. Redeploy after changing them. `.env.example` lists names and safe defaults only; do not add real values to that file or frontend code. Local secret files and `.vercel/` are ignored by Git.

| Variable | Purpose / default |
| --- | --- |
| `PAYPAL_CLIENT_ID` | Required to check out. REST app client ID; this public identifier is returned to the browser for the SDK. |
| `PAYPAL_CLIENT_SECRET` | Required to check out. Server-only OAuth credential; also signs this store's order snapshots. |
| `PAYPAL_ENVIRONMENT` | `sandbox` (default) or explicitly `live`. Selects `https://api-m.sandbox.paypal.com` or `https://api-m.paypal.com`. |
| `PAYPAL_WEBHOOK_ID` | Required for webhook verification. The ID of the webhook registered on this exact REST app and environment. |
| `RESEND_API_KEY` | Required for internal order notifications; server-only. |
| `STORE_CURRENCY` | Optional, `USD` by default. Supported two-decimal currencies: `USD`, `CAD`, `EUR`, `GBP`, `AUD`, `NZD`. Match `currency` in the display catalog. Other currencies fail closed. |
| `STORE_ALLOWED_ORIGINS` | Optional comma-separated replacement allowlist. Defaults to the three production origins and localhost origins below. |
| `STORE_ORDER_TO_EMAIL` | Internal order recipient; falls back to `REQUEST_TO_EMAIL`. |
| `STORE_ORDER_FROM_EMAIL` | Verified Resend sender; falls back to `REQUEST_FROM_EMAIL`. |
| `STORE_SHIPPING_FLAT_CENTS` | Optional nonnegative integer, default `0`; charged once per order. |

Default allowed origins are `https://minipcb.com`, `https://www.minipcb.com`, `https://minipcb.github.io`, and `http://localhost` / `http://127.0.0.1` on ports `3000`, `4173`, and `5500`, matching the contact endpoint's development convention. Browser endpoints require an allowed `Origin`, including for preflights; absent origins are rejected. Add a preview site's exact origin when testing there. Webhooks are server-to-server and use signature verification instead of CORS.

### Endpoints and checkout

| Method and endpoint | Purpose |
| --- | --- |
| `GET /api/paypal-create-order` | Public SDK configuration: client ID, environment, currency, flat shipping, and checkout availability. Never returns a secret. Reuses the create endpoint to avoid another serverless function. |
| `POST /api/paypal-create-order` | Accepts `{"items":[{"sku":"04A-006-KIT","quantity":2}]}`; returns `paypalOrderId`. |
| `POST /api/paypal-capture-order` | Accepts `{"paypalOrderId":"..."}`; verifies, captures or reconciles the order, and returns a minimal payment result. |
| `POST /api/paypal-webhook` | Verifies the PayPal signature, retrieves the trusted order, and handles `PAYMENT.CAPTURE.COMPLETED` notifications. |

The browser SDK approves payments; only Vercel creates and captures them. Browser configuration follows the existing site precedence: `apiBase` query parameter, then `localStorage.tb26_api_base`, then `https://minipcb-github-io.vercel.app/api`. Store links preserve query overrides. These public endpoints do not require or expose `PROXY_KEY`.

### Pricing, shipping, and activation

1. Define the explicitly approved, nonzero integer price in `STORE_PRODUCTS` in [`api/_paypal.js`](api/_paypal.js). This catalog is authoritative.
2. Set that product's `active` to `true` on the backend. Unknown, inactive, zero-price, duplicate, or invalid-quantity lines are rejected. Quantities are integers from 1 to 99 per SKU.
3. Match the price, currency, revision, and `active` flag in [`../store/products.js`](../store/products.js). This second catalog is for display only. Setting only the frontend flag never enables server checkout.
4. Confirm product descriptions and kit contents; update the store's availability introduction when ordering opens. The existing component-layout image is illustrative, not a photograph of kit contents.
5. Configure the flat shipping amount and your fulfillment coverage before activation. Shipping is currently the same for every address PayPal supplies; there are no destination restrictions, carrier quotes, tax calculations, discounts, inventory reservations, or stock counters. These rules are centralized in `_paypal.js` if they need to change.
6. Deploy the backend and matching frontend, then test using Sandbox before enabling live mode.

Prices and totals use integer cents internally. Browser-supplied monetary fields are ignored. Each PayPal purchase unit carries a signed snapshot of the SKU, revision-bearing name, quantity, unit price, currency, shipping, and unique reference. Before capture, the server retrieves the order from PayPal, checks the signature and amount breakdown, and rechecks current prices and availability. Price or availability changes stop an uncaptured checkout. Completed payments continue to reconcile against their original signed prices, even if a product has since been deactivated. Rotating the PayPal client secret invalidates old snapshot signatures; reconcile outstanding orders before rotation.

### Sandbox setup and end-to-end testing

1. In the [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/), create/select a **Sandbox** REST app for a sandbox business account. Use a separate sandbox personal account as the buyer.
2. Set its client ID and secret in the Vercel deployment, explicitly set `PAYPAL_ENVIRONMENT=sandbox`, and configure Resend with a verified sender and your internal order recipient.
3. Register `https://minipcb-github-io.vercel.app/api/paypal-webhook` (or your test deployment's corresponding URL) on that sandbox app, subscribing to `PAYMENT.CAPTURE.COMPLETED`. Set its ID as `PAYPAL_WEBHOOK_ID` and redeploy.
4. For a separate test deployment, set `STORE_ALLOWED_ORIGINS` for its frontend. Activate a test SKU with an explicitly chosen test price in both catalogs on that test branch/deployment. Keep the production catalogs inactive until actual prices are approved.
5. Open the store with `?apiBase=https://YOUR-TEST-DEPLOYMENT.vercel.app/api`. Add products, change quantities, refresh the cart, and confirm the server amount and shipping address in PayPal. The checkout message must say **Sandbox checkout**.
6. Approve with the sandbox buyer. Verify the success page, cleared cart, completed capture in the sandbox merchant dashboard, and internal email (including item lines, shipping, amount, and customer details).
7. Cancel an approval and confirm the cart is preserved. Retry a capture request for a completed order and confirm there is no second capture. Simulate a lost response and use **Check payment status** after refreshing the cart.
8. Verify an actual signed sandbox webhook and its delivery result in PayPal. Simulator events are not a substitute for this signature test. Missing headers, missing webhook configuration, and unsuccessful verification fail closed.
9. Temporarily break the test deployment's email configuration: a completed payment must still return success, and `store_order_email_failed` must appear in Vercel logs. The webhook returns non-2xx on notification failure so PayPal can retry. Restore the email settings and redeliver the webhook to recover the notice.

No real Sandbox transaction has been executed as part of the repository's offline checks. Actual credentials, deployment, buyer approval, and signed webhook delivery are required for the end-to-end steps above.

### Switching to live

After the Sandbox checklist passes, deliberately configure the live REST app's client ID, secret, and webhook ID; register the live webhook URL and event; set `PAYPAL_ENVIRONMENT=live`; confirm approved nonzero prices and `active: true` in both catalogs; and redeploy. Verify the public configuration from the actual frontend origin and complete a controlled live purchase before announcing ordering. There is no automatic sandbox-to-live switch. To stop new sales, deactivate the backend SKUs and redeploy, then update frontend availability.

### Payment recovery, notification, and fulfillment

- A `COMPLETED` capture with the verified full amount is paid. A pending or unconfirmed result never clears the cart. The browser retains an unresolved order ID in session storage and offers **Check payment status** so it can retry that same order after a lost response.
- Capture requests use a stable `PayPal-Request-Id` for the order and reconcile an already-completed capture. They do not recapture pending payments. The success page uses a receipt created after an API confirmation; a URL parameter alone cannot establish payment status. Local receipts are display aids, never fulfillment evidence.
- Internal email uses the existing Resend REST pattern, with a capture-specific `Idempotency-Key` and a bounded warm-instance cache. Provider idempotency lasts [24 hours](https://resend.com/docs/dashboard/emails/idempotency-keys); it is not a permanent duplicate-notification or fulfillment guarantee. Both capture and verified webhook paths produce the same notice from PayPal's order details.
- **Payment success is independent of email delivery.** Notification failures are logged separately, and the completed capture is returned to the buyer. Verified completed-payment webhooks provide a recovery path if the browser disconnects or capture-time notification fails. Monitor `store_order_email_failed` / `store_webhook` logs and PayPal deliveries; redeliver failed events after fixing the cause.
- PayPal is the payment record. This first store has no durable local order ledger, automatic fulfillment, refunds UI, or dispute workflow. Before shipping, verify the capture in the merchant dashboard and record the capture ID in your fulfillment records. Do not ship twice based on repeated emails. Add durable capture/fulfillment tracking before automating shipping.
- CORS narrows browser access; it is not authentication or bot protection. Monetary validation and signed PayPal order verification enforce the payment boundary. No provider response bodies, tokens, or customer addresses are logged or returned publicly. Customer details are sent only to the configured internal email recipient. Enable appropriate Vercel request limits if public traffic warrants it.

### Repeatable local checks

From the repository root:

```sh
node proxy-vercel/tests/paypal.test.js
node store/tests/serve.js
```

Open `http://127.0.0.1:5500/store/tests/browser.html` for real-browser cart, navigation, checkout cancellation, and recovery checks. The browser harness runs only on localhost and mocks PayPal/API responses; test catalog activation occurs in memory only. No production prices or credentials are changed, and no test sends a payment or email.

Integration references: [PayPal Orders v2](https://developer.paypal.com/api/orders/v2), [official JavaScript SDK v5 controls](https://developer.paypal.com/sdk/js/v5/reference/), [webhook verification](https://developer.paypal.com/api/rest/webhooks), and [Vercel function duration](https://vercel.com/docs/functions/configuring-functions/duration).

That’s it—GitHub Pages stays static, and Vercel handles the proxy.
