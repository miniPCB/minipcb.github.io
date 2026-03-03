const { setCors, requireProxyKey } = require("./_utils");

const DIGIKEY_TOKEN_SAFETY_MS = 30 * 1000;
const AVAILABILITY_CACHE_TTL_MS = Number(process.env.AVAILABILITY_CACHE_TTL_MS || 5 * 60 * 1000);

let digikeyTokenCache = {
  token: "",
  expiresAt: 0
};

const availabilityCache = new Map();

function cleanPartNumber(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 180);
}

function normalizePartNumber(value) {
  return cleanPartNumber(value).toUpperCase();
}

function asText(value, maxLen) {
  return String(value == null ? "" : value)
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLen || 240);
}

function toNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (value == null) return null;
  const cleaned = String(value).replace(/[^0-9.\-]/g, "");
  if (!cleaned) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function parseQuantityFromAvailabilityText(value) {
  const text = asText(value, 240);
  if (!text) return null;
  const m = text.match(/(\d[\d,]*)/);
  if (!m) return null;
  const qty = toNumber(m[1].replace(/,/g, ""));
  return qty == null ? null : Math.max(0, Math.floor(qty));
}

function byPath(obj, path) {
  const keys = path.split(".");
  let cur = obj;
  for (const key of keys) {
    if (!cur || typeof cur !== "object" || !Object.prototype.hasOwnProperty.call(cur, key)) return undefined;
    cur = cur[key];
  }
  return cur;
}

function firstPath(obj, paths) {
  for (const path of paths) {
    const value = byPath(obj, path);
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

function makeTimeoutController(timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  return { controller, timeout };
}

function readCachedAvailability(key) {
  const hit = availabilityCache.get(key);
  if (!hit) return null;
  if (hit.expiresAt <= Date.now()) {
    availabilityCache.delete(key);
    return null;
  }
  return hit.value;
}

function writeCachedAvailability(key, value) {
  availabilityCache.set(key, {
    value,
    expiresAt: Date.now() + AVAILABILITY_CACHE_TTL_MS
  });
}

async function requestDigikeyToken() {
  const now = Date.now();
  if (digikeyTokenCache.token && digikeyTokenCache.expiresAt > now + DIGIKEY_TOKEN_SAFETY_MS) {
    return digikeyTokenCache.token;
  }

  const clientId = process.env.DIGIKEY_CLIENT_ID;
  const clientSecret = process.env.DIGIKEY_CLIENT_SECRET;
  const tokenUrl = process.env.DIGIKEY_TOKEN_URL || "https://api.digikey.com/v1/oauth2/token";

  if (!clientId || !clientSecret) {
    throw new Error("DigiKey credentials are not configured.");
  }

  const body = new URLSearchParams({
    grant_type: "client_credentials",
    client_id: clientId,
    client_secret: clientSecret
  });

  // Primary flow: credentials in form body.
  let response;
  let payloadText = "";
  {
    const { controller, timeout } = makeTimeoutController(12000);
    try {
      response = await fetch(tokenUrl, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
        signal: controller.signal
      });
      payloadText = await response.text();
    } finally {
      clearTimeout(timeout);
    }
  }

  // Fallback flow: credentials via HTTP Basic.
  if (!response.ok) {
    const basic = Buffer.from(`${clientId}:${clientSecret}`).toString("base64");
    const { controller, timeout } = makeTimeoutController(12000);
    try {
      response = await fetch(tokenUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Authorization: `Basic ${basic}`
        },
        body: new URLSearchParams({ grant_type: "client_credentials" }).toString(),
        signal: controller.signal
      });
      payloadText = await response.text();
    } finally {
      clearTimeout(timeout);
    }
  }

  if (!response.ok) {
    throw new Error(`DigiKey token error (${response.status}).`);
  }

  let tokenJson = {};
  try {
    tokenJson = payloadText ? JSON.parse(payloadText) : {};
  } catch (_err) {
    tokenJson = {};
  }

  const accessToken = asText(tokenJson.access_token || tokenJson.AccessToken, 2048);
  const expiresIn = toNumber(tokenJson.expires_in || tokenJson.ExpiresIn) || 1800;
  if (!accessToken) {
    throw new Error("DigiKey token response did not include access_token.");
  }

  digikeyTokenCache = {
    token: accessToken,
    expiresAt: Date.now() + Math.max(60, Math.floor(expiresIn)) * 1000
  };
  return accessToken;
}

function normalizeDigikeyResponse(partNumber, body) {
  const product = firstPath(body, ["Product", "product", "Products.0", "products.0"]) || body;
  const qty = toNumber(
    firstPath(product, [
      "QuantityAvailable",
      "quantityAvailable",
      "QuantityOnHand",
      "quantityOnHand",
      "Stock",
      "stock",
      "AvailableQuantity",
      "availableQuantity"
    ])
  );
  const availabilityText = asText(
    firstPath(product, ["Availability", "availability", "AvailabilityStatus", "availabilityStatus"]),
    240
  );
  const quantity = qty == null ? parseQuantityFromAvailabilityText(availabilityText) : Math.max(0, Math.floor(qty));
  const manufacturerPartNumber = asText(
    firstPath(product, ["ManufacturerPartNumber", "manufacturerPartNumber", "ManufacturerProductNumber"]),
    180
  );
  const distributorPartNumber = asText(
    firstPath(product, ["DigiKeyPartNumber", "digiKeyPartNumber", "DigiKeyProductNumber", "ProductNumber"]),
    180
  );
  const productUrl = asText(firstPath(product, ["ProductUrl", "productUrl", "ProductUrl2"]), 700);

  return {
    source: "digikey",
    status: "ok",
    queriedPartNumber: partNumber,
    manufacturerPartNumber: manufacturerPartNumber || partNumber,
    distributorPartNumber: distributorPartNumber || "",
    availabilityText: availabilityText || (quantity == null ? "" : `${quantity} available`),
    quantity: quantity == null ? null : quantity,
    productUrl: productUrl || ""
  };
}

async function fetchDigikeyAvailability(partNumber) {
  const clientId = process.env.DIGIKEY_CLIENT_ID;
  const clientSecret = process.env.DIGIKEY_CLIENT_SECRET;
  if (!clientId || !clientSecret) {
    return {
      source: "digikey",
      status: "skipped",
      queriedPartNumber: partNumber,
      error: "DigiKey credentials not configured."
    };
  }

  try {
    const token = await requestDigikeyToken();
    const apiBase = process.env.DIGIKEY_API_BASE || "https://api.digikey.com";
    const localeSite = process.env.DIGIKEY_SITE || "US";
    const localeLanguage = process.env.DIGIKEY_LANGUAGE || "en";
    const localeCurrency = process.env.DIGIKEY_CURRENCY || "USD";
    const url = `${apiBase}/products/v4/search/${encodeURIComponent(partNumber)}/productdetails`;

    const { controller, timeout } = makeTimeoutController(15000);
    let response;
    let text = "";
    try {
      response = await fetch(url, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          "X-DIGIKEY-Client-Id": clientId,
          "X-DIGIKEY-Locale-Site": localeSite,
          "X-DIGIKEY-Locale-Language": localeLanguage,
          "X-DIGIKEY-Locale-Currency": localeCurrency
        },
        signal: controller.signal
      });
      text = await response.text();
    } finally {
      clearTimeout(timeout);
    }

    if (response.status === 404) {
      return {
        source: "digikey",
        status: "not_found",
        queriedPartNumber: partNumber,
        error: "Part not found."
      };
    }
    if (!response.ok) {
      return {
        source: "digikey",
        status: "error",
        queriedPartNumber: partNumber,
        error: `DigiKey request failed (${response.status}).`
      };
    }

    let body = {};
    try {
      body = text ? JSON.parse(text) : {};
    } catch (_err) {
      body = {};
    }
    return normalizeDigikeyResponse(partNumber, body);
  } catch (err) {
    return {
      source: "digikey",
      status: "error",
      queriedPartNumber: partNumber,
      error: asText(err && err.message ? err.message : err, 240)
    };
  }
}

async function mouserSearchRaw(apiKey, payload) {
  const searchUrl = (process.env.MOUSER_SEARCH_URL || "https://api.mouser.com/api/v1/search/partnumber").trim();
  const url = `${searchUrl}${searchUrl.includes("?") ? "&" : "?"}apiKey=${encodeURIComponent(apiKey)}`;
  const { controller, timeout } = makeTimeoutController(15000);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    const text = await response.text();
    let body = {};
    try {
      body = text ? JSON.parse(text) : {};
    } catch (_err) {
      body = {};
    }
    return { response, body };
  } finally {
    clearTimeout(timeout);
  }
}

function selectBestMouserPart(parts, queryPartNumber) {
  const normalizedQuery = normalizePartNumber(queryPartNumber);
  if (!parts.length) return null;

  const score = (part) => {
    const mfr = normalizePartNumber(part.ManufacturerPartNumber || part.manufacturerPartNumber);
    const mouser = normalizePartNumber(part.MouserPartNumber || part.mouserPartNumber);
    if (mfr === normalizedQuery || mouser === normalizedQuery) return 5;
    if (mfr && normalizedQuery && (mfr.includes(normalizedQuery) || normalizedQuery.includes(mfr))) return 4;
    if (mouser && normalizedQuery && (mouser.includes(normalizedQuery) || normalizedQuery.includes(mouser))) return 3;
    return 0;
  };

  let best = parts[0];
  let bestScore = score(best);
  for (let i = 1; i < parts.length; i += 1) {
    const s = score(parts[i]);
    if (s > bestScore) {
      best = parts[i];
      bestScore = s;
    }
  }
  return best;
}

function normalizeMouserResponse(partNumber, body) {
  const parts = firstPath(body, ["SearchResults.Parts", "searchResults.parts", "SearchResults.parts"]) || [];
  if (!Array.isArray(parts) || !parts.length) {
    return {
      source: "mouser",
      status: "not_found",
      queriedPartNumber: partNumber,
      error: "Part not found."
    };
  }

  const part = selectBestMouserPart(parts, partNumber) || parts[0];
  const availabilityText = asText(part.Availability || part.availability, 240);
  const qtyFields = [
    part.AvailabilityInStock,
    part.availabilityInStock,
    part.FactoryStock,
    part.factoryStock,
    part.InStock,
    part.inStock
  ];
  let quantity = null;
  for (const candidate of qtyFields) {
    const n = toNumber(candidate);
    if (n != null) {
      quantity = Math.max(0, Math.floor(n));
      break;
    }
  }
  if (quantity == null) {
    quantity = parseQuantityFromAvailabilityText(availabilityText);
  }

  return {
    source: "mouser",
    status: "ok",
    queriedPartNumber: partNumber,
    manufacturerPartNumber: asText(part.ManufacturerPartNumber || part.manufacturerPartNumber, 180),
    distributorPartNumber: asText(part.MouserPartNumber || part.mouserPartNumber, 180),
    availabilityText: availabilityText || (quantity == null ? "" : `${quantity} available`),
    quantity: quantity == null ? null : quantity,
    productUrl: asText(part.ProductDetailUrl || part.productDetailUrl, 700)
  };
}

async function fetchMouserAvailability(partNumber) {
  const apiKey = process.env.MOUSER_API_KEY;
  if (!apiKey) {
    return {
      source: "mouser",
      status: "skipped",
      queriedPartNumber: partNumber,
      error: "Mouser API key not configured."
    };
  }

  try {
    const payloads = [
      { SearchByPartRequest: { mouserPartNumber: partNumber, partSearchOptions: "" } },
      { SearchByPartnumberRequest: { MouserPartNumber: partNumber, partSearchOptions: "" } }
    ];

    let bestBody = null;
    let hadHttpError = false;
    for (const payload of payloads) {
      const { response, body } = await mouserSearchRaw(apiKey, payload);
      if (!response.ok) {
        hadHttpError = true;
        continue;
      }
      bestBody = body;
      const parts = firstPath(body, ["SearchResults.Parts", "searchResults.parts", "SearchResults.parts"]) || [];
      if (Array.isArray(parts) && parts.length) {
        return normalizeMouserResponse(partNumber, body);
      }
    }

    if (bestBody) {
      return normalizeMouserResponse(partNumber, bestBody);
    }
    if (hadHttpError) {
      return {
        source: "mouser",
        status: "error",
        queriedPartNumber: partNumber,
        error: "Mouser request failed."
      };
    }
    return {
      source: "mouser",
      status: "not_found",
      queriedPartNumber: partNumber,
      error: "Part not found."
    };
  } catch (err) {
    return {
      source: "mouser",
      status: "error",
      queriedPartNumber: partNumber,
      error: asText(err && err.message ? err.message : err, 240)
    };
  }
}

module.exports = async (req, res) => {
  setCors(res);
  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ ok: false, error: "Method not allowed." });
  if (!requireProxyKey(req, res)) return;

  const rawPartNumber = req.body && typeof req.body === "object" ? req.body.partNumber : "";
  const partNumber = cleanPartNumber(rawPartNumber);
  if (!partNumber) {
    return res.status(400).json({ ok: false, error: "partNumber is required." });
  }

  const cacheKey = normalizePartNumber(partNumber);
  const cached = readCachedAvailability(cacheKey);
  if (cached) {
    return res.status(200).json({ ...cached, cached: true });
  }

  try {
    const [digikey, mouser] = await Promise.all([
      fetchDigikeyAvailability(partNumber),
      fetchMouserAvailability(partNumber)
    ]);

    const responseBody = {
      ok: true,
      cached: false,
      partNumber,
      normalizedPartNumber: cacheKey,
      timestamp: new Date().toISOString(),
      digikey,
      mouser
    };
    writeCachedAvailability(cacheKey, responseBody);
    return res.status(200).json(responseBody);
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: "Failed to load availability.",
      detail: asText(err && err.message ? err.message : err, 240)
    });
  }
};

