const OPENAI_BASE = "https://api.openai.com";

function setCors(res){
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, X-Proxy-Key");
}

function requireProxyKey(req, res){
  const required = process.env.PROXY_KEY;
  if(required){
    const provided = req.headers["x-proxy-key"];
    if(provided !== required){
      res.status(401).json({ error: "Unauthorized" });
      return false;
    }
  }
  return true;
}

async function forward(res, method, path, body){
  const key = process.env.OPENAI_API_KEY;
  if(!key){
    res.status(500).json({ error: "OPENAI_API_KEY is not set." });
    return;
  }
  const resp = await fetch(`${OPENAI_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${key}`
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const text = await resp.text();
  res.status(resp.status);
  const ct = resp.headers.get("content-type");
  if(ct) res.setHeader("Content-Type", ct);
  res.send(text);
}

module.exports = { setCors, requireProxyKey, forward };
