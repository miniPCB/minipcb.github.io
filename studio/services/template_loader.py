import re, json
from pathlib import Path

class Templates:
    def __init__(self, root: Path):
        self.root = Path(root)
        reg = self.root / "templates.json"
        if not reg.exists():
            raise FileNotFoundError(f"Missing {reg}.")
        self.registry = json.loads(reg.read_text(encoding="utf-8"))

    def render_key(self, key: str, ctx: dict) -> str:
        path = self.root / self.registry["defaults"][key]
        text = path.read_text(encoding="utf-8")
        text = self._expand_partials(text)
        text = self._replace(text, ctx)
        text = self._strip_if_blocks(text, ctx)
        return text

    # --- helpers ---
    def _expand_partials(self, text: str) -> str:
        pat = re.compile(r"\{\{>\s*([^}]+?)\s*\}\}")
        def repl(m):
            p = self.root / m.group(1).strip()
            return p.read_text(encoding="utf-8") if p.exists() else ""
        return pat.sub(repl, text)

    def _replace(self, text: str, ctx: dict) -> str:
        def repl(m):
            key = m.group(1).strip()
            return str(ctx.get(key, ""))
        return re.sub(r"\{\{\s*([A-Za-z0-9_\.]+)\s*\}\}", repl, text)

    def _strip_if_blocks(self, text: str, ctx: dict) -> str:
        # very small {{#if key}}...{{/if}} impl
        pat = re.compile(r"\{\{#if\s+([^}]+)\}\}([\s\S]*?)\{\{/if\}\}")
        def repl(m):
            key = m.group(1).strip()
            return m.group(2) if ctx.get(key) else ""
        return pat.sub(repl, text)
