# minipcb_catalog/services/template_loader.py
from pathlib import Path
import re, json

class Templates:
    _re_partial = re.compile(r"\{\{\>\s*([^\}]+?)\s*\}\}")
    _re_token   = re.compile(r"\{\{([A-Z0-9_]+?)(?:\|([^}]*))?\}\}")  # {{KEY|default}}
    _re_if      = re.compile(r"<!--\s*IF:([A-Z0-9_]+)\s*-->(.*?)<!--\s*ENDIF\s*-->", re.S)
    _re_ifnot   = re.compile(r"<!--\s*IFNOT:([A-Z0-9_]+)\s*-->(.*?)<!--\s*ENDIF\s*-->", re.S)
    _re_unfilled= re.compile(r"\{\{[A-Z0-9_]+(?:\|[^}]*)?\}\}")

    def __init__(self, root: Path, *, error_on_unfilled: bool = False, max_include_depth: int = 8):
        """
        :param root: templates/ directory
        :param error_on_unfilled: if True, raise when placeholders remain after render
        :param max_include_depth: safety limit for nested partials
        """
        self.root = Path(root)
        reg = self.root / "templates.json"
        if not reg.exists():
            raise FileNotFoundError(f"Missing {reg}.")
        self.registry = json.loads(reg.read_text(encoding="utf-8"))
        self._cache: dict[Path, str] = {}
        self._error_on_unfilled = error_on_unfilled
        self._max_include_depth = max_include_depth

    # --- public API ---------------------------------------------------------

    def render_key(self, key: str, ctx: dict) -> str:
        rel = self.registry["defaults"][key]
        return self.render_path(rel, ctx)

    def render_path(self, relpath: str, ctx: dict) -> str:
        """Render a template by relative path within templates/."""
        path = self._safe_path(relpath)
        text = self._read(path)
        text = self._expand_partials(text, depth=self._max_include_depth)
        text = self._strip_if_blocks(text, ctx)
        text = self._replace(text, ctx)
        if self._error_on_unfilled and self._re_unfilled.search(text):
            # Helpful message including first leftover token
            m = self._re_unfilled.search(text)
            left = m.group(0) if m else "{{...}}"
            raise ValueError(f"Unfilled token {left} in {relpath}")
        return text

    def pick_html_key_for_filename(self, filename: str) -> str:
        """
        XX.html or XXX.html → collection; otherwise detail.
        """
        return "html_collection" if re.fullmatch(r"[A-Za-z0-9]{2,3}\.html", filename) else "html_detail"

    # --- helpers ------------------------------------------------------------

    def _read(self, path: Path) -> str:
        cached = self._cache.get(path)
        if cached is not None:
            return cached
        text = path.read_text(encoding="utf-8")
        self._cache[path] = text
        return text

    def _safe_path(self, rel: str) -> Path:
        """
        Prevent path traversal in partials/includes.
        """
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError(f"Unsafe include outside templates root: {rel}")
        if not p.exists():
            raise FileNotFoundError(f"Template not found: {rel}")
        return p

    def _expand_partials(self, text: str, *, depth: int) -> str:
        """
        Expand {{> path/to/file.html }} up to 'depth' levels.
        """
        if depth <= 0:
            return text
        def repl(m):
            rel = m.group(1).strip()
            p = self._safe_path(rel)
            t = self._read(p)
            # Recurse so partials can include partials (bounded by depth-1)
            return self._expand_partials(t, depth=depth-1)
        # Replace all partials found at this level, then return.
        return self._re_partial.sub(repl, text)

    def _replace(self, text: str, ctx: dict) -> str:
        """
        Replace {{KEY}} and {{KEY|default}} with values from ctx, defaulting to
        the fallback if missing/empty. Values are inserted as-is (no escaping).
        """
        def repl(m):
            key = m.group(1)
            default = m.group(2) if m.group(2) is not None else ""
            val = ctx.get(key, None)
            if val is None or val == "":
                return default
            return str(val)
        return self._re_token.sub(repl, text)

    def _strip_if_blocks(self, text: str, ctx: dict) -> str:
        """
        Support:
          <!-- IF:FLAG --> ... <!-- ENDIF -->
          <!-- IFNOT:FLAG --> ... <!-- ENDIF -->
        Truthiness: bool(val) from ctx (strings like "0" are truthy unless empty).
        """
        def yes(m):
            flag = m.group(1)
            body = m.group(2)
            return body if bool(ctx.get(flag, False)) else ""
        def no(m):
            flag = m.group(1)
            body = m.group(2)
            return "" if bool(ctx.get(flag, False)) else body
        text = self._re_if.sub(yes, text)
        text = self._re_ifnot.sub(no, text)
        return text
