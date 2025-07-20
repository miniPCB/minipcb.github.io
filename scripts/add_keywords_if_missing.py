import os
import re
from bs4 import BeautifulSoup
from collections import Counter

def suggest_keywords(text, max_keywords=10):
    # Simple frequency-based keyword extractor
    words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())  # 4+ letter words
    stopwords = set(['html', 'head', 'body', 'with', 'this', 'that', 'from', 'about', 'your', 'page', 'will', 'have', 'more', 'please', 'check'])
    filtered = [word for word in words if word not in stopwords]
    common = Counter(filtered).most_common(max_keywords)
    return ", ".join(word for word, _ in common)

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    head = soup.head
    if not head:
        print(f"⛔ No <head> found in {filepath}")
        return

    title = soup.title.string.strip() if soup.title else ''
    meta_keywords = head.find("meta", attrs={"name": "keywords"})

    if meta_keywords:
        print(f"✅ Keywords already present in {filepath}")
        return

    # Extract visible content for keyword suggestion
    content_text = ' '.join(tag.get_text() for tag in soup.find_all(['h1', 'h2', 'h3', 'p', 'li']))
    combined_text = f"{title} {content_text}"
    suggested = suggest_keywords(combined_text)

    # Create and insert <meta name="keywords">
    new_meta = soup.new_tag("meta")
    new_meta.attrs['name'] = "keywords"
    new_meta.attrs['content'] = suggested
    head.append(new_meta)

    # Write back updated HTML
    with open(filepath, 'w', encoding='utf-8') as file:
        file.write(str(soup.prettify()))

    print(f"✏️ Added keywords to {filepath}: {suggested}")

# Walk entire directory
for root, _, files in os.walk("."):
    for file in files:
        if file.endswith(".html"):
            full_path = os.path.join(root, file)
            process_file(full_path)
