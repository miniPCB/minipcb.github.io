from pathlib import Path
from bs4 import BeautifulSoup

class HtmlService:
    def __init__(self, templates):
        self.templates = templates

    def extract_metadata(self, html_text: str) -> dict:
        soup = BeautifulSoup(html_text, "html.parser")
        meta = {
            "pn": soup.find(id="pn").text.strip() if soup.find(id="pn") else "",
            "title": soup.title.text.strip() if soup.title else "",
            "seo": {
                "slogan": self._meta_content(soup, "slogan"),
                "keywords": self._meta_content(soup, "keywords").split(",") if self._meta_content(soup, "keywords") else [],
                "description": self._meta_content(soup, "description"),
            },
            "nav": [],
            "revisions": []
        }
        nav = soup.select("nav a")
        for a in nav:
            meta["nav"].append({"text": a.get_text(strip=True), "url": a.get("href", "#")})
        # revisions table by id
        table = soup.find(id="revision_history")
        if table:
            rows = table.select("tbody tr") or table.select("tr")[1:]
            for tr in rows:
                tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(tds) >= 4:
                    meta["revisions"].append({"date": tds[0], "rev": tds[1], "desc": tds[2], "by": tds[3]})
        return meta

    def apply_metadata(self, html_text: str, data: dict) -> str:
        soup = BeautifulSoup(html_text, "html.parser")
        if soup.title and data.get("title"):
            soup.title.string = data["title"]
        # meta seo
        self._set_meta(soup, "slogan", data.get("seo", {}).get("slogan", ""))
        self._set_meta(soup, "keywords", ",".join(data.get("seo", {}).get("keywords", [])))
        self._set_meta(soup, "description", data.get("seo", {}).get("description", ""))
        # nav
        nav = soup.find("nav")
        if nav and data.get("nav"):
            nav.clear()
            for item in data["nav"]:
                a = soup.new_tag("a", href=item.get("url","#"))
                a.string = item.get("text","")
                nav.append(a)
            # spacing
            nav.append(soup.new_string("\n"))
        # revisions
        table = soup.find(id="revision_history")
        if table and data.get("revisions"):
            tbody = table.find("tbody") or table
            if tbody.name != "tbody":
                # wrap if needed
                tb = soup.new_tag("tbody")
                for tr in list(tbody.find_all("tr"))[1:]:
                    tb.append(tr.extract())
                table.append(tb)
                tbody = tb
            tbody.clear()
            for r in data["revisions"]:
                tr = soup.new_tag("tr")
                for key in ("date","rev","desc","by"):
                    td = soup.new_tag("td")
                    td.string = r.get(key,"")
                    tr.append(td)
                tbody.append(tr)
        return str(soup)

    def build_new_shell(self, ctx: dict) -> str:
        # page shell (base) which expands partials
        return self.templates.render_key("page_shell", ctx)

    # helpers
    def _meta_content(self, soup, name: str) -> str:
        m = soup.find("meta", attrs={"name": name})
        return m.get("content","") if m else ""

    def _set_meta(self, soup, name: str, value: str):
        if not value:
            return
        m = soup.find("meta", attrs={"name": name})
        if not m:
            m = soup.new_tag("meta", **{"name":name, "content": value})
            soup.head.append(m)
        else:
            m["content"] = value
