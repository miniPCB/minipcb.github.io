import os

FAVICON_TAG = '  <link rel="icon" href="/favicon.png" type="image/png" />\n'
TARGET_TAG = '</head>'

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.readlines()

    # Check if favicon line is already there
    if any('rel="icon"' in line for line in content):
        return  # Already has favicon, skip

    modified = []
    inserted = False

    for line in content:
        if TARGET_TAG in line and not inserted:
            modified.append(FAVICON_TAG)
            inserted = True
        modified.append(line)

    if inserted:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(modified)
        print(f"✅ Updated: {filepath}")
    else:
        print(f"⚠️  No </head> found in: {filepath}")

def main():
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.html'):
                filepath = os.path.join(root, file)
                process_file(filepath)

if __name__ == '__main__':
    main()
