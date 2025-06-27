import sys
import os
import openai
from bs4 import BeautifulSoup

# ✅ Set your API key in the environment like this (before running):
# $env:OPENAI_API_KEY = "sk-..."

# Initialize OpenAI client (for openai>=1.0.0)
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_data(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    slogan = soup.find("p", class_="slogan")
    slogan_text = slogan.get_text(strip=True) if slogan else "(No slogan found)"

    details_section = soup.find("div", {"id": "details"})
    detail_lines = []
    if details_section:
        for p in details_section.find_all("p"):
            label = p.find("strong")
            if label:
                key = label.get_text(strip=True).rstrip(":")
                value = label.next_sibling.strip() if label.next_sibling else ""
                detail_lines.append(f"{key}: {value}")

    return slogan_text, "\n".join(detail_lines)

def generate_overview(slogan, details):
    prompt = f"""
You are writing an AI-generated educational overview for a PCB used in electronics instruction.

Slogan: "{slogan}"

PCB Details:
{details}

Write a <div id='ai-overview' class='tab-content'> HTML block that includes:
1. What the circuit does.
2. How it works (basic functional description).
3. Where it's used in real life.
4. Key learning outcomes for students.
5. A short list of follow-up questions students can explore.

Use proper HTML tags like <h2>, <p>, and <ul>, but do not include <html>, <head>, or <body>.
"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    return response.choices[0].message.content.strip()

def insert_ai_overview(html_path, overview_html):
    print(f"[INFO] Inserting AI Overview into: {html_path}")

    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    tab_container = soup.find("div", class_="tab-container")
    if not tab_container:
        print(f"[ERROR] No .tab-container found in {html_path}")
        return

    # ✅ Add the AI Overview tab button
    tabs_div = tab_container.find("div", class_="tabs")
    inserted_tab = False
    if tabs_div:
        tab_buttons = tabs_div.find_all("button")
        existing = [btn.get("onclick", "") for btn in tab_buttons]

        if not any("ai-overview" in e for e in existing):
            new_tab = soup.new_tag("button", attrs={
                "class": "tab",
                "onclick": "showTab('ai-overview')"
            })
            new_tab.string = "AI Overview"

            insert_index = None
            for i, btn in enumerate(tab_buttons):
                if "downloads" in btn.get("onclick", ""):
                    insert_index = i
                    break

            if insert_index is not None:
                tab_buttons[insert_index].insert_before(soup.new_string("\n"))
                tab_buttons[insert_index].insert_before(new_tab)
                inserted_tab = True
                print(f"[OK] Inserted <button> AI Overview tab")
        else:
            print(f"[SKIP] AI Overview tab already present")

    else:
        print(f"[WARN] No <div class='tabs'> found")

    # ✅ Add the AI Overview content block
    new_div = BeautifulSoup(overview_html, "html.parser")
    tab_container.append(new_div)
    print(f"[OK] Inserted <div id='ai-overview'> content")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(str(soup))

    print(f"[DONE] Updated file saved: {html_path}\\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python gen_ai_overview.py file1.html [file2.html ...]")
        return

    for html_file in sys.argv[1:]:
        try:
            slogan, details = extract_data(html_file)
            print(f"Generating overview for {html_file}...")
            overview_html = generate_overview(slogan, details)
            insert_ai_overview(html_file, overview_html)
        except Exception as e:
            print(f"[ERROR] {html_file}: {str(e)}")

if __name__ == "__main__":
    main()
