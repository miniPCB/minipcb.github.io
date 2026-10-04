const { STORE_PRODUCTS, settings, browserRequest, payload, calculateOrder, createOrderBody, paypalRequest, validateOrderId, reportError, randomUUID } = require("./_paypal");

module.exports = async (req, res) => {
  if (!browserRequest(req, res, ["GET", "POST"])) return;
  try {
    // Public SDK configuration; the client secret is deliberately excluded.
    if (req.method === "GET") {
      const config = settings(false);
      return res.status(200).json({ ok: true, clientId: config.clientId || "", environment: config.environment, currency: config.currency, shippingFlatCents: config.shippingFlatCents, checkoutEnabled: Boolean(config.clientId && config.clientSecret && Object.values(STORE_PRODUCTS).some(p => p.active && p.priceCents > 0)) });
    }
    const order = calculateOrder(payload(req).items);
    const created = await paypalRequest("/v2/checkout/orders", { method: "POST", body: createOrderBody(order), requestId: randomUUID() });
    validateOrderId(created.id);
    return res.status(200).json({ ok: true, paypalOrderId: created.id });
  } catch (error) { return reportError(res, error, "store_create_order"); }
};
