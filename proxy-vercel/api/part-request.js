const { setCors, requireProxyKey } = require("./_utils");

function isEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || "").trim());
}

function cleanLine(value, maxLen) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLen);
}

function cleanBlock(value, maxLen) {
  return String(value || "")
    .replace(/\r\n/g, "\n")
    .trim()
    .slice(0, maxLen);
}

function parsePayload(body) {
  const payload = body && typeof body === "object" ? body : {};
  return {
    name: cleanLine(payload.name, 120),
    email: cleanLine(payload.email, 180),
    organization: cleanLine(payload.organization, 160),
    family: cleanLine(payload.family, 120),
    partNumber: cleanLine(payload.partNumber || payload.requestedPart, 180),
    details: cleanBlock(payload.details, 3000)
  };
}

function validatePayload(payload) {
  if (!payload.name) return "Name is required.";
  if (!payload.email || !isEmail(payload.email)) return "A valid email is required.";
  if (!payload.family) return "Component family is required.";
  if (!payload.partNumber) return "Requested part number/pattern is required.";
  if (!payload.details) return "Details are required.";
  return "";
}

async function sendWithResend(payload) {
  const apiKey = process.env.RESEND_API_KEY;
  const toEmail = process.env.REQUEST_TO_EMAIL;
  const fromEmail = process.env.REQUEST_FROM_EMAIL;

  if (!apiKey) throw new Error("RESEND_API_KEY is not set.");
  if (!toEmail) throw new Error("REQUEST_TO_EMAIL is not set.");
  if (!fromEmail) throw new Error("REQUEST_FROM_EMAIL is not set.");

  const subject = `Part Request: ${payload.partNumber}`;
  const text = [
    "New part request submission",
    "",
    `Name: ${payload.name}`,
    `Email: ${payload.email}`,
    `Organization: ${payload.organization || "(not provided)"}`,
    `Family: ${payload.family}`,
    `Requested Part/Pattern: ${payload.partNumber}`,
    "",
    "Details:",
    payload.details
  ].join("\n");

  const resp = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      from: fromEmail,
      to: [toEmail],
      reply_to: payload.email,
      subject,
      text
    })
  });

  if (!resp.ok) {
    const msg = await resp.text();
    throw new Error(`Resend error (${resp.status}): ${msg}`);
  }
}

module.exports = async (req, res) => {
  setCors(res);
  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ ok: false, error: "Method not allowed." });
  if (!requireProxyKey(req, res)) return;

  try {
    const payload = parsePayload(req.body);
    const validationError = validatePayload(payload);
    if (validationError) return res.status(400).json({ ok: false, error: validationError });

    await sendWithResend(payload);
    return res.status(200).json({ ok: true });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: "Failed to send part request.",
      detail: String(err && err.message ? err.message : err)
    });
  }
};

