import os
from bs4 import BeautifulSoup
import openai

# Load API key from environment variable
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise EnvironmentError("OPENAI_API_KEY environment variable not set.")

# New client-based API for openai>=1.0.0
client = openai.OpenAI(api_key=api_key)

def extract_text_for_prompt(soup):
    content = []

    # Title
    if soup.title:
        content.append(f"Title: {soup.title.string.strip()}")

    # Headings
    for tag in soup.find_all(['h1', 'h2']):
        text = tag.get_text(strip=True)
        if text:
            content.append(f"Heading: {text}")

    # Image alt text
    for img in soup.find_all('img'):
        alt = img.get('alt')
        if alt:
            content.append(f"Image Alt: {alt.strip()}")

    # Slogan
    slogan = soup.find('p', class_='slogan')
    if slogan:
        slogan_text = slogan.get_text(strip=True)
        content.append(f"Slogan: {slogan_text}")

    return '\n'.join(content)

def get_ai_keywords(text):
    prompt = (
        "Based on the following HTML page content (title, headings, slogan, image alt text), "
        "generate a list of 10 to 20 concise, comma-separated SEO keywords that are relevant to the page:\n\n"
        f"{text}\n\nKeywords:"
    )

    response = client.chat.completions.create(
        model="gpt-4",  # or "gpt-3.5-turbo"
        messages=[
            {"role": "system", "content": "You are an expert SEO assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    return response.choices[0].message.content.strip()

def update_keywords_in_html(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')
    text_for_prompt = extract_text_for_prompt(soup)
    if not text_for_prompt.strip():
        print(f"[!] Skipped (no useful content): {filepath}")
        return

    keywords = get_ai_keywords(text_for_prompt)

    meta_tag = soup.find('meta', attrs={'name': 'keywords'})
    if meta_tag:
        meta_tag['content'] = keywords
    else:
        head = soup.find('head')
        if head:
            new_meta = soup.new_tag('meta', attrs={'name': 'keywords', 'content': keywords})
            title_tag = head.find('title')
            if title_tag:
                title_tag.insert_after(new_meta)
            else:
                head.append(new_meta)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(str(soup))

    print(f"[✓] AI keywords updated: {filepath}")

def find_html_files(root_dir):
    for dirpath, _, filenames in os.walk(root_dir):
        for file in filenames:
            if file.endswith('.html'):
                yield os.path.join(dirpath, file)

if __name__ == '__main__':
    root_directory = '.'  # Change this path if needed
    for html_file in find_html_files(root_directory):
        update_keywords_in_html(html_file)
