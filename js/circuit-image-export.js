/* Local image exports; SVG stays vector, raster images use the same snapshot. */
(function (root) {
  "use strict";
  const formats = Object.freeze({ svg: ["image/svg+xml", "svg"], png: ["image/png", "png"], jpeg: ["image/jpeg", "jpg"], bmp: ["image/bmp", "bmp"] });

  function rasterSize(width, height) {
    if (![width, height].every(value => Number.isFinite(value) && value > 0)) throw new Error("The circuit has no image dimensions.");
    const scale = Math.min(2, 8192 / width, 8192 / height, Math.sqrt(16000000 / width / height));
    return { width: Math.max(1, Math.floor(width * scale)), height: Math.max(1, Math.floor(height * scale)) };
  }

  function bitmap(pixels) {
    // Windows BITMAPFILEHEADER + BITMAPINFOHEADER, uncompressed 24-bit BGR.
    // https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapinfoheader
    const { width, height, data } = pixels, stride = Math.ceil(width * 3 / 4) * 4, size = stride * height;
    const bytes = new Uint8Array(54 + size), view = new DataView(bytes.buffer);
    bytes[0] = 0x42; bytes[1] = 0x4d;
    view.setUint32(2, bytes.length, true); view.setUint32(10, 54, true); view.setUint32(14, 40, true);
    view.setInt32(18, width, true); view.setInt32(22, height, true); view.setUint16(26, 1, true); view.setUint16(28, 24, true);
    view.setUint32(34, size, true); view.setInt32(38, 3780, true); view.setInt32(42, 3780, true);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const from = (y * width + x) * 4, to = 54 + (height - 1 - y) * stride + x * 3;
      bytes[to] = data[from + 2]; bytes[to + 1] = data[from + 1]; bytes[to + 2] = data[from];
    }
    return new Blob([bytes], { type: formats.bmp[0] });
  }

  async function encode(snapshot, format) {
    if (!Object.hasOwn(formats, format)) throw new Error("Choose an image format.");
    const svg = new Blob([snapshot.markup], { type: formats.svg[0] });
    if (format === "svg") return svg;
    const size = rasterSize(snapshot.width, snapshot.height), canvas = document.createElement("canvas");
    canvas.width = size.width; canvas.height = size.height;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("Image export is unavailable in this browser.");
    const url = URL.createObjectURL(svg), image = new Image();
    try {
      await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = () => reject(new Error("The circuit image could not be rendered.")); image.src = url; });
      context.fillStyle = "#101823"; context.fillRect(0, 0, size.width, size.height); context.drawImage(image, 0, 0, size.width, size.height);
      if (format === "bmp") return bitmap(context.getImageData(0, 0, size.width, size.height));
      const blob = await new Promise(resolve => canvas.toBlob(resolve, formats[format][0], 0.95));
      if (!blob || blob.type !== formats[format][0]) throw new Error("This browser cannot export that image format.");
      return blob;
    } finally { image.onload = image.onerror = null; URL.revokeObjectURL(url); canvas.width = canvas.height = 0; }
  }

  function filename(title, format) {
    const stem = title.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "").slice(0, 64).toLowerCase() || "voltage_divider";
    return `${stem}_circuit.${formats[format][1]}`;
  }

  root.CircuitImageExport = Object.freeze({ formats, rasterSize, bitmap, encode, filename });
})(globalThis);
