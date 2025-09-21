from __future__ import annotations
import json, re

def read_ai_seeds_from_html(html: str) -> dict:
    m = re.search(r'(<script[^>]+id=["\']ai-seeds-json["\'][^>]*>)(.*?)(</script>)', html or "", re.I | re.S)
    if not m:
        return {"description_seed": "", "fmea_seed": "", "testing": {"dtp_seed": "", "atp_seed": ""}}
    try:
        data = json.loads(m.group(2).strip())
        fmea_seed = data.get("fmea_seed")
        if fmea_seed is None:
            fmea_obj = data.get("fmea", {})
            parts = [fmea_obj.get(k, "") for k in ("L0", "L1", "L2", "L3")]
            fmea_seed = "\n\n".join([p for p in parts if (p or '').strip()])
        testing = data.get("testing", {})
        return {
            "description_seed": data.get("description_seed", ""),
            "fmea_seed": fmea_seed or "",
            "testing": {
                "dtp_seed": testing.get("dtp_seed", ""),
                "atp_seed": testing.get("atp_seed", "")
            }
        }
    except Exception:
        return {"description_seed": "", "fmea_seed": "", "testing": {"dtp_seed": "", "atp_seed": ""}}

def write_ai_seeds_to_html(html: str, seeds: dict) -> str:
    payload = {
        "description_seed": seeds.get("description_seed", ""),
        "fmea_seed": seeds.get("fmea_seed", ""),
        "testing": {
            "dtp_seed": seeds.get("testing", {}).get("dtp_seed", ""),
            "atp_seed": seeds.get("testing", {}).get("atp_seed", "")
        }
    }
    json_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    m = re.search(r'(<script[^>]+id=["\']ai-seeds-json["\'][^>]*>)(.*?)(</script>)', html or "", re.I | re.S)
    if not m:
        block = (
            '\n<div id="ai-seeds" class="tab-content" data-hidden="true">\n'
            f'  <script type="application/json" id="ai-seeds-json">{json_text}</script>\n'
            '</div>\n'
        )
        if "</main>" in (html or ""):
            return (html or "").replace("</main>", block + "</main>", 1)
        if "</body>" in (html or ""):
            return (html or "").replace("</body>", block + "</body>", 1)
        return (html or "") + block
    return (html or "")[:m.start(2)] + json_text + (html or "")[m.end(2):]
