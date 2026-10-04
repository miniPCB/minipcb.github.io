const { StoreError, payload, validateOrderId, accessToken, paypalRequest, verifyOrder, completedCapture, sendOrderNotice, reportError } = require("./_paypal");

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") { res.setHeader("Allow", "POST"); return res.status(405).json({ ok: false, error: "Method not allowed." }); }
  try {
    const event = payload(req, 262144);
    const webhookId = process.env.PAYPAL_WEBHOOK_ID;
    if (!webhookId) throw new StoreError(503, "Webhook verification is not configured.");
    const fields = { auth_algo: "paypal-auth-algo", cert_url: "paypal-cert-url", transmission_id: "paypal-transmission-id", transmission_sig: "paypal-transmission-sig", transmission_time: "paypal-transmission-time" };
    const verification = { webhook_id: webhookId, webhook_event: event };
    for (const [field, header] of Object.entries(fields)) {
      const value = req.headers[header];
      if (typeof value !== "string" || !value || value.length > 4096) throw new StoreError(400, "Missing or invalid webhook signature headers.");
      verification[field] = value;
    }
    // We never fetch the supplied certificate URL ourselves.
    const token = await accessToken();
    const verified = await paypalRequest("/v1/notifications/verify-webhook-signature", { method: "POST", body: verification, token });
    if (verified.verification_status !== "SUCCESS") throw new StoreError(403, "Webhook signature verification failed.");
    if (event.event_type !== "PAYMENT.CAPTURE.COMPLETED") return res.status(200).json({ ok: true, ignored: true });
    const id = validateOrderId(event.resource?.supplementary_data?.related_ids?.order_id);
    const order = await paypalRequest(`/v2/checkout/orders/${id}`, { token });
    if (!String(order.purchase_units?.[0]?.custom_id || "").startsWith("minipcb-v1:")) return res.status(200).json({ ok: true, ignored: true });
    const snapshot = verifyOrder(order);
    const capture = completedCapture(order, snapshot);
    if (order.id !== id || !capture || capture.id !== event.resource?.id) throw new StoreError(409, "Webhook capture does not match the order.");
    // A non-2xx response on email failure asks PayPal to retry; payment remains paid.
    await sendOrderNotice(order, snapshot, capture);
    return res.status(200).json({ ok: true });
  } catch (error) { return reportError(res, error, "store_webhook"); }
};
