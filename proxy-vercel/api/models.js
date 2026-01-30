const { setCors, requireProxyKey, forward } = require("./_utils");

module.exports = async (req, res) => {
  setCors(res);
  if(req.method === "OPTIONS") return res.status(204).end();
  if(req.method !== "GET") return res.status(405).json({ error: "Method not allowed" });
  if(!requireProxyKey(req, res)) return;
  try{
    await forward(res, "GET", "/v1/models", null);
  }catch(err){
    res.status(500).json({ error: String(err.message || err) });
  }
};
