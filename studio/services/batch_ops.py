from pathlib import Path
from .file_service import FileService
from .template_loader import Templates
from .html_service import HtmlService

class BatchOps:
    def __init__(self, site_root: Path, templates_dir: Path):
        self.root = Path(site_root)
        self.templates = Templates(templates_dir)
        self.html = HtmlService(self.templates)
        self.fs = FileService(site_root)

    def update_all_html(self):
        for p in self.root.rglob("*.html"):
            self.update_one_html(p)

    def update_one_html(self, path: Path):
        html = self.fs.read_text(path)
        data = self.html.extract_metadata(html)
        new_shell = self.html.build_new_shell({
            "TITLE": data.get("title",""),
            "PN": data.get("pn",""),
            "SLOGAN": data.get("seo",{}).get("slogan",""),
            "KEYWORDS": ",".join(data.get("seo",{}).get("keywords",[])),
            "DESCRIPTION": data.get("seo",{}).get("description",""),
        })
        merged = self.html.apply_metadata(new_shell, data)
        self.fs.write_text_atomic(path, merged)
