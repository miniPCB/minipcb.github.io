const { StoreError, browserRequest, payload, validateOrderId, calculateOrder, verifyOrder, accessToken, paypalRequest, completedCapture, normalizedOrder, sendOrderNotice, reportError } = require("./_paypal");

function unresolvedStatus(order) {
  const captures = order.purchase_units[0].payments?.captures || [];
  if (!captures.length || captures.some(item => item.status === "PENDING")) return "PENDING";
  if (captures.every(item => ["DECLINED", "FAILED"].includes(item.status))) return "NOT_COMPLETED";
  return "REVIEW_REQUIRED";
}

module.exports = async (req, res) => {
  if (!browserRequest(req, res)) return;
  try {
    const id = validateOrderId(payload(req).paypalOrderId);
    const token = await accessToken();
    const path = `/v2/checkout/orders/${id}`;
    let order = await paypalRequest(path, { token });
    if (order.id !== id) throw new StoreError(409, "Order could not be verified.");
    const snapshot = verifyOrder(order);
    let capture = completedCapture(order, snapshot);
    if (!capture) {
      // Do not initiate another capture for a pending payment.
      if (order.purchase_units[0].payments?.captures?.length) {
        return res.status(200).json({ ok: true, status: unresolvedStatus(order), paypalOrderId: id });
      }
      if (order.status !== "APPROVED") throw new StoreError(409, "Approve the order in PayPal before completing payment.");
      const current = calculateOrder(snapshot.items);
      if (JSON.stringify(current) !== JSON.stringify(snapshot)) throw new StoreError(409, "Prices or availability changed. Contact miniPCB about this order before paying again.");
      let captured;
      try {
        captured = await paypalRequest(`${path}/capture`, { method: "POST", body: {}, requestId: `minipcb-capture-${id}`, token });
      } catch (error) {
        // A timeout or concurrent request may have captured successfully. Reconcile first.
        order = await paypalRequest(path, { token });
        verifyOrder(order);
        capture = completedCapture(order, snapshot);
        if (!capture) throw error;
      }
      if (captured) {
        if (captured.id !== id) throw new StoreError(409, "Payment confirmation needs review. Contact miniPCB before paying again.");
        // Capture responses may omit items; retain the verified pre-capture snapshot.
        order = { ...order, ...captured, purchase_units: [{ ...order.purchase_units[0], ...captured.purchase_units?.[0] }] };
        capture = completedCapture(order, snapshot);
      }
    }
    if (!capture) {
      const status = unresolvedStatus(order);
      return res.status(status === "PENDING" ? 202 : 200).json({ ok: true, status, paypalOrderId: id });
    }
    try {
      // Use the same canonical GET representation in both capture and webhook notices.
      const noticeOrder = await paypalRequest(path, { token });
      const noticeSnapshot = verifyOrder(noticeOrder);
      const noticeCapture = completedCapture(noticeOrder, noticeSnapshot);
      if (!noticeCapture || noticeCapture.id !== capture.id) throw new StoreError(502, "Order notification is awaiting confirmation.");
      await sendOrderNotice(noticeOrder, noticeSnapshot, noticeCapture);
    }
    catch (error) { console.error("store_order_email_failed", { paypalOrderId: id, captureId: capture.id, code: error.code || "EMAIL_ERROR" }); }
    // Email failure never changes a successful payment into a failed checkout.
    return res.status(200).json({ ok: true, ...normalizedOrder(order, snapshot, capture) });
  } catch (error) { return reportError(res, error, "store_capture_order"); }
};
