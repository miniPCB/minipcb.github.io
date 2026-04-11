const DEFAULT_ALLOWED_ORIGINS = [
  "https://minipcb.com",
  "https://www.minipcb.com",
  "https://minipcb.github.io",
  "http://localhost:3000",
  "http://127.0.0.1:3000",
  "http://localhost:4173",
  "http://127.0.0.1:4173",
  "http://localhost:5500",
  "http://127.0.0.1:5500"
];

const recentSubmissions = globalThis.__minipcbContactRecentSubmissions || new Map();
globalThis.__minipcbContactRecentSubmissions = recentSubmissions;

function parsePositiveNumber(value, fallback, minValue) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(minValue, parsed);
}

const RATE_LIMIT_WINDOW_MS = parsePositiveNumber(process.env.CONTACT_RATE_WINDOW_MS, 15 * 60 * 1000, 60_000);
const RATE_LIMIT_MAX = parsePositiveNumber(process.env.CONTACT_RATE_MAX, 5, 1);

function normalizeOrigin(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function getAllowedOrigins() {
  const fromEnv = String(process.env.CONTACT_ALLOWED_ORIGINS || "").trim();
  const raw = fromEnv ? fromEnv.split(",") : DEFAULT_ALLOWED_ORIGINS;
  return raw.map(normalizeOrigin).filter(Boolean);
}

function isAllowedOrigin(origin) {
  if (!origin) return true;
  return getAllowedOrigins().includes(normalizeOrigin(origin));
}

function setCors(req, res) {
  const origin = normalizeOrigin(req.headers.origin);
  if (origin && isAllowedOrigin(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
  } else if (!origin) {
    res.setHeader("Access-Control-Allow-Origin", "*");
  }

  res.setHeader("Access-Control-Allow-Methods", "POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
}

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
    subject: cleanLine(payload.subject, 180),
    website: cleanLine(payload.website, 200),
    message: cleanBlock(payload.message, 4000)
  };
}

function validatePayload(payload) {
  if (payload.website) return "Spam check failed.";
  if (!payload.name) return "Name is required.";
  if (!payload.email || !isEmail(payload.email)) return "A valid email is required.";
  if (!payload.message) return "Message is required.";
  if (payload.message.length < 10) return "Message must be at least 10 characters.";
  return "";
}

function getClientIp(req) {
  const forwarded = String(req.headers["x-forwarded-for"] || "").trim();
  if (forwarded) return forwarded.split(",")[0].trim();
  return String(req.socket && req.socket.remoteAddress ? req.socket.remoteAddress : "").trim();
}

function isRateLimited(ip) {
  if (!ip) return false;
  const now = Date.now();
  const recent = (recentSubmissions.get(ip) || []).filter((ts) => now - ts < RATE_LIMIT_WINDOW_MS);
  if (recent.length >= RATE_LIMIT_MAX) {
    recentSubmissions.set(ip, recent);
    return true;
  }
  recent.push(now);
  recentSubmissions.set(ip, recent);
  return false;
}

async function sendWithResend(payload, req) {
  const apiKey = process.env.RESEND_API_KEY;
  const toEmail = process.env.CONTACT_TO_EMAIL || process.env.REQUEST_TO_EMAIL;
  const fromEmail = process.env.CONTACT_FROM_EMAIL || process.env.REQUEST_FROM_EMAIL;
  const subjectPrefix = cleanLine(process.env.CONTACT_SUBJECT_PREFIX || "Website Contact", 120) || "Website Contact";

  if (!apiKey) throw new Error("RESEND_API_KEY is not set.");
  if (!toEmail) throw new Error("CONTACT_TO_EMAIL or REQUEST_TO_EMAIL must be set.");
  if (!fromEmail) throw new Error("CONTACT_FROM_EMAIL or REQUEST_FROM_EMAIL must be set.");

  const subject = payload.subject ? `${subjectPrefix}: ${payload.subject}` : `${subjectPrefix}: ${payload.name}`;
  const text = [
    "New website contact form submission",
    "",
    `Name: ${payload.name}`,
    `Email: ${payload.email}`,
    `Organization: ${payload.organization || "(not provided)"}`,
    `Subject: ${payload.subject || "(not provided)"}`,
    `Origin: ${normalizeOrigin(req.headers.origin) || "(not provided)"}`,
    `IP: ${getClientIp(req) || "(not provided)"}`,
    "",
    "Message:",
    payload.message
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
  setCors(req, res);

  if (req.method === "OPTIONS") {
    if (!isAllowedOrigin(req.headers.origin)) {
      return res.status(403).json({ ok: false, error: "Origin not allowed." });
    }
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ ok: false, error: "Method not allowed." });
  }

  if (!isAllowedOrigin(req.headers.origin)) {
    return res.status(403).json({ ok: false, error: "Origin not allowed." });
  }

  try {
    const payload = parsePayload(req.body);
    const validationError = validatePayload(payload);
    if (validationError) return res.status(400).json({ ok: false, error: validationError });

    if (isRateLimited(getClientIp(req))) {
      return res.status(429).json({ ok: false, error: "Too many messages sent recently. Please try again later." });
    }

    await sendWithResend(payload, req);
    return res.status(200).json({ ok: true });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: "Failed to send contact message.",
      detail: String(err && err.message ? err.message : err)
    });
  }
};
