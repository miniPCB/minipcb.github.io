// Local static server for browser checks: node store/tests/serve.js
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../..");
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".jpg": "image/jpeg" };
http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:5500");
  const file = path.resolve(root, "." + decodeURIComponent(url.pathname === "/" ? "/store/index.html" : url.pathname));
  if (!file.startsWith(root + path.sep)) { res.writeHead(403); res.end(); return; }
  fs.readFile(file, (error, bytes) => {
    if (error) { res.writeHead(404); res.end("Not found"); return; }
    res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream", "Cache-Control": "no-store" });
    res.end(bytes);
  });
}).listen(5500, "127.0.0.1", () => console.log("Store: http://127.0.0.1:5500/store/index.html\nChecks: http://127.0.0.1:5500/store/tests/browser.html"));
