const { setCors } = require("./_utils");

module.exports = async (req, res) => {
  setCors(res);
  if(req.method === "OPTIONS") return res.status(204).end();
  res.status(200).json({ ok: true });
};
