const OPENAI_BASE = "https://api.openai.com";

function withCors(resp){
  const headers = new Headers(resp.headers);
  headers.set("Access-Control-Allow-Origin", "*");
  headers.set("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  headers.set("Access-Control-Allow-Headers", "Content-Type, X-Proxy-Key");
  return new Response(resp.body, { status: resp.status, headers });
}

function jsonResp(obj, status=200){
  return withCors(new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json" }
  }));
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if(request.method === "OPTIONS"){
      return withCors(new Response(null, { status: 204 }));
    }

    if(env.PROXY_KEY){
      const key = request.headers.get("X-Proxy-Key");
      if(key !== env.PROXY_KEY){
        return jsonResp({ error: "Unauthorized" }, 401);
      }
    }

    if(!env.OPENAI_API_KEY){
      return jsonResp({ error: "OPENAI_API_KEY is not set on the Worker." }, 500);
    }

    if(url.pathname === "/api/health"){
      return jsonResp({ ok: true });
    }

    if(url.pathname === "/api/models" && request.method === "GET"){
      const resp = await fetch(`${OPENAI_BASE}/v1/models`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${env.OPENAI_API_KEY}` }
      });
      return withCors(resp);
    }

    if(["/api/review","/api/suggest","/api/chat","/api/create"].includes(url.pathname) && request.method === "POST"){
      const body = await request.text();
      const resp = await fetch(`${OPENAI_BASE}/v1/responses`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${env.OPENAI_API_KEY}`
        },
        body
      });
      return withCors(resp);
    }

    return jsonResp({ error: "Not found" }, 404);
  }
};
