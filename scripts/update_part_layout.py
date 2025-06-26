import os
import re

# === CONFIGURATION ===
folders = ["./04A"]  # <-- Replace with your actual folder paths

# === HTML Template ===
TAB_TEMPLATE = """
<main>

  <div class="tab-container">
    <div class="tabs">
      <button class="tab active" onclick="showTab('details')">Details</button>
      <button class="tab" onclick="showTab('schematic')">Schematic</button>
      <button class="tab" onclick="showTab('layout')">Layout</button>
      <button class="tab" onclick="showTab('downloads')">Downloads</button>
      <button class="tab" onclick="showTab('resources')">Additional Resources</button>
    </div>

    <div id="details" class="tab-content active">
      <h2>PCB Details</h2>
      <p><strong>Part No:</strong> {part_no}</p>
      <p><strong>Title:</strong> {title}</p>
      <p><strong>Board Size:</strong> {board_size}</p>
      <p><strong>Pieces per Panel:</strong> {pieces}</p>
      <p><strong>Panel Size:</strong> {panel_size}</p>
    </div>

    <div id="schematic" class="tab-content">
      <h2>Schematic</h2>
      <div class="lightbox-container">
        <img src="../images/{img_base}_schematic_01.png" alt="Schematic" class="zoomable" onclick="openLightbox(this)" />
      </div>
      <div id="lightbox" onclick="closeLightbox()">
        <img id="lightbox-img" src="" alt="Expanded schematic" />
      </div>
    </div>

    <div id="layout" class="tab-content">
      <h2>Board Layout</h2>
      <img src="../images/{img_base}_components_top.png" alt="Top view of miniPCB" class="zoomable" />
    </div>

    <div id="downloads" class="tab-content">
      <h2>Datasheet</h2>
      <a href="{datasheet}" target="_blank">Download Datasheet</a>
    </div>

    <div id="resources" class="tab-content">
      <h2>YouTube</h2><p>Coming soon...</p>
      <h2>Wikipedia</h2><p>Coming soon...</p>
      <h2>Instructables</h2><p>Coming soon...</p>
    </div>
  </div>

</main>
"""

def extract_between(content, tag_start, tag_end):
    match = re.search(re.escape(tag_start) + r"(.*?)" + re.escape(tag_end), content, re.DOTALL)
    return match.group(1).strip() if match else ""

def convert_file(path):
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    part_no = os.path.splitext(os.path.basename(path))[0]
    img_base = part_no.replace(".html", "")
    print(f"Processing: {part_no}")

    # Extract fields
    title = re.search(r"<h1>(.*?)</h1>", html)
    title = title.group(1).strip() if title else "Unknown"

    board_size = re.search(r"Board Size:</strong>\s*(.*?)<", html)
    board_size = board_size.group(1).strip() if board_size else "N/A"

    pieces = re.search(r"Pieces per Panel:</strong>\s*([^<]*)", html)
    pieces = pieces.group(1).strip() if pieces else "N/A"

    panel_size = re.search(r"Panel Size:</strong>\s*([^<]*)", html)
    panel_size = panel_size.group(1).strip() if panel_size else "N/A"

    datasheet = re.search(r'<a href="([^"]*?datasheets/[^"]+)"', html)
    datasheet = datasheet.group(1).strip() if datasheet else "../datasheets/coming-soon.html"

    objectives_block = extract_between(html, "<ul>", "</ul>")
    objectives = "\n        ".join([f"<li>{o.strip()}</li>" for o in re.findall(r"<li>(.*?)</li>", objectives_block)])

    # Build new <main> section
    new_main = TAB_TEMPLATE.format(
        part_no=part_no,
        title=title,
        board_size=board_size,
        pieces=pieces,
        panel_size=panel_size,
        datasheet=datasheet,
        objectives=objectives,
        img_base=img_base
    )

    # Replace the old <main>...</main> section
    updated = re.sub(r"<main>.*?</main>", new_main, html, flags=re.DOTALL)

    # Inject required JS if not already present
    if "function showTab(" not in updated:
        js_block = """
    <script>
        function showTab(id) {
        document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
        document.getElementById(id).classList.add('active');
        event.currentTarget.classList.add('active');
        }
    </script>
    <script>
        function openLightbox(img) {
        document.getElementById('lightbox-img').src = img.src;
        document.getElementById('lightbox').style.display = 'flex';
        }
        function closeLightbox() {
        document.getElementById('lightbox').style.display = 'none';
        }
    </script>
    """
        updated = updated.replace("</body>", js_block + "\n</body>")

    # Save it back
    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)


def run():
    for folder in folders:
        for filename in os.listdir(folder):
            if filename.endswith(".html"):
                convert_file(os.path.join(folder, filename))

if __name__ == "__main__":
    run()
