const express = require("express");
const cors = require("cors");

const app = express();
const PORT = process.env.PORT || 8787;
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";
const PROXY_KEY = process.env.PROXY_KEY || "";

app.use(cors({ origin: "*", methods: ["GET", "POST"], allowedHeaders: ["Content-Type", "X-Proxy-Key"] }));
app.use(express.json({ limit: "2mb" }));

function requireProxyKey(req, res, next){
  if(PROXY_KEY && req.headers["x-proxy-key"] !== PROXY_KEY){
    return res.status(401).json({ error: "Unauthorized" });
  }
  next();
}

async function forward(method, path, body, res){
  if(!OPENAI_API_KEY){
    return res.status(500).json({ error: "OPENAI_API_KEY is not set on the server." });
  }
  const resp = await fetch(`https://api.openai.com${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${OPENAI_API_KEY}`
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const text = await resp.text();
  res.status(resp.status);
  const ct = resp.headers.get("content-type");
  if(ct) res.type(ct);
  res.send(text);
}

app.get("/api/health", (_req, res) => {
  res.json({ ok: true });
});

app.get("/api/models", requireProxyKey, async (_req, res) => {
  try{
    await forward("GET", "/v1/models", null, res);
  }catch(err){
    res.status(500).json({ error: String(err.message || err) });
  }
});

app.post("/api/review", requireProxyKey, async (req, res) => {
  try{
    await forward("POST", "/v1/responses", req.body, res);
  }catch(err){
    res.status(500).json({ error: String(err.message || err) });
  }
});

app.post("/api/suggest", requireProxyKey, async (req, res) => {
  try{
    await forward("POST", "/v1/responses", req.body, res);
  }catch(err){
    res.status(500).json({ error: String(err.message || err) });
  }
});

app.post("/api/chat", requireProxyKey, async (req, res) => {
  try{
    await forward("POST", "/v1/responses", req.body, res);
  }catch(err){
    res.status(500).json({ error: String(err.message || err) });
  }
});

app.post("/api/create", requireProxyKey, async (req, res) => {
  try{
    await forward("POST", "/v1/responses", req.body, res);
  }catch(err){
    res.status(500).json({ error: String(err.message || err) });
  }
});

app.listen(PORT, () => {
  console.log(`OpenAI proxy listening on http://localhost:${PORT}`);
});
