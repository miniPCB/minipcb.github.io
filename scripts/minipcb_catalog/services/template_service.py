# minipcb_catalog/services/template_service.py
"""
TemplateService — render new Board / Collection pages.

- Looks for templates on disk first: templates/page_board.html, templates/page_collection.html
- If missing, uses built-in minimal templates (with required section markers)
- Tokens: {{TITLE}}, {{PN}}, {{REV}}, {{DATE}}
- Adds <meta name="minipcb:type" content="board|collection">
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict

from ..app import AppContext
from .. import constants

_BUILTIN_BOARD = f"""<!DOCTYPE html>
<html><head>
  <meta charset="utf-8">
  <meta name="minipcb:type" content="board">
  <title>{{{{TITLE}}}}</title>
  <meta name="keywords" content="">
  <link rel="stylesheet" href="/styles.css">
</head><body>
<h1>{{{{TITLE}}}} ({{{{PN}}}} {{REV}})</h1>
<span class="status-tag">Draft</span>

{constants.SECTIONS["details"]["begin"]}
<p></p>
{constants.SECTIONS["details"]["end"]}

{constants.SECTIONS["circuit_description"]["begin"]}
<p></p>
{constants.SECTIONS["circuit_description"]["end"]}

{constants.SECTIONS["resources"]["begin"]}
<ul><li></li></ul>
{constants.SECTIONS["resources"]["end"]}

{constants.SECTIONS["downloads"]["begin"]}
<ul><li></li></ul>
{constants.SECTIONS["downloads"]["end"]}

{constants.SECTIONS["dtp"]["begin"]}
<p></p>
{constants.SECTIONS["dtp"]["end"]}

<img id="schematic" src="">
<img id="layout" src="">

<footer>&copy; {{{{DATE}}}} miniPCB</footer>
</body></html>
"""

_BUILTIN_COLLECTION = f"""<!DOCTYPE html>
<html><head>
  <meta charset="utf-8">
  <meta name="minipcb:type" content="collection">
  <title>{{{{TITLE}}}}</title>
  <meta name="keywords" content="">
  <link rel="stylesheet" href="/styles.css">
</head><body>
<h1>{{{{TITLE}}}}</h1>
<span class="status-tag">Collection</span>

{constants.SECTIONS["details"]["begin"]}
<p>Collection overview.</p>
{constants.SECTIONS["details"]["end"]}

{constants.SECTIONS["resources"]["begin"]}
<ul><li></li></ul>
{constants.SECTIONS["resources"]["end"]}

{constants.SECTIONS["downloads"]["begin"]}
<ul><li></li></ul>
{constants.SECTIONS["downloads"]["end"]}

<footer>&copy; {{{{DATE}}}} miniPCB</footer>
</body></html>
"""

@dataclass(slots=True)
class TemplateTokens:
    title: str
    pn: str = ""
    rev: str = ""
    date: str = ""

class TemplateService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.templates_dir = Path(__file__).resolve().parents[1] / "templates"

    def _load_template(self, name: str) -> str:
        # name in {"page_board.html", "page_collection.html"}
        candidate = self.templates_dir / name
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
        return _BUILTIN_BOARD if name == "page_board.html" else _BUILTIN_COLLECTION

    def render_board(self, title: str, pn: str, rev: str) -> str:
        tpl = self._load_template("page_board.html")
        return (tpl
                .replace("{{TITLE}}", title)
                .replace("{{PN}}", pn)
                .replace("{{REV}}", rev)
                .replace("{{DATE}}", date.today().strftime("%Y")))

    def render_collection(self, title: str) -> str:
        tpl = self._load_template("page_collection.html")
        return (tpl
                .replace("{{TITLE}}", title)
                .replace("{{PN}}", "")
                .replace("{{REV}}", "")
                .replace("{{DATE}}", date.today().strftime("%Y")))
