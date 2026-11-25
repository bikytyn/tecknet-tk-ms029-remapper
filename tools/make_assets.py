"""Builds assets/mouse.png (mouse photo without background) + assets/mouse.json (control positions).

Vyrobí fotku myši bez pozadí a polohy ovladačů. Source: a 3/4 product photo of the TK-MS029 on a white
background (1200×1500 px, the same framing as the original – hotspot coordinates below depend on it).

Usage:  python tools/make_assets.py path/to/photo.jpg
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "..", "..", "vstupy", "ftoky myši", "61meMz+q8lL.jpg")
OUT = os.path.join(ROOT, "assets")

# polohy ovladačů ve zdrojové fotce (px)
HOTSPOTS = {"h": (712, 650), "x2": (697, 786), "x1": (797, 716),
            # ovladače s nastavením Windows: kolečko; levé a pravé tlačítko = zrcadlově přes dělicí drážku
            "wheel": (304, 682), "lbtn": (173, 859), "rbtn": (95, 781),
            "bfork": (122, 620)}  # bod vidličky čar k L a P tlačítku (nad obrysem myši)


def main():
    im = Image.open(os.path.normpath(SRC)).convert("RGB")
    w, h = im.size
    # 1) pozadí = bílá oblast spojená s okrajem obrázku
    probe = im.copy()
    key = (255, 0, 255)
    for xy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        if probe.getpixel(xy) != key:
            ImageDraw.floodfill(probe, xy, key, thresh=40)
    obj = Image.new("L", (w, h), 0)
    op, pp = obj.load(), probe.load()
    for y in range(h):
        for x in range(w):
            if pp[x, y] != key:
                op[x, y] = 255
    # 2) měkký okraj + odstranění bílého lemu (unmatte proti bílé)
    obj = obj.filter(ImageFilter.MinFilter(5))  # oříznout světlý lem z JPEG artefaktů
    alpha = obj.filter(ImageFilter.GaussianBlur(1.0))
    ap = alpha.load()
    rgba = im.convert("RGBA")
    rp = rgba.load()
    for y in range(h):
        for x in range(w):
            a = ap[x, y]
            if a == 0:
                rp[x, y] = (0, 0, 0, 0)
            elif a < 255:
                af = a / 255.0
                r, g, b, _ = rp[x, y]
                un = [max(0, min(255, int((c - (1 - af) * 255) / af))) for c in (r, g, b)]
                rp[x, y] = (*un, a)
            else:
                r, g, b, _ = rp[x, y]
                rp[x, y] = (r, g, b, 255)
    # 3) ořez
    bbox = rgba.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    m = 10
    box = (max(0, bbox[0] - m), max(0, bbox[1] - m), min(w, bbox[2] + m), min(h, bbox[3] + m))
    rgba = rgba.crop(box)
    os.makedirs(OUT, exist_ok=True)
    rgba.save(os.path.join(OUT, "mouse.png"), optimize=True)
    # varianta pro tmavý motiv – zesvětlená, aby černá myš nesplynula s pozadím
    rgb, a = rgba.convert("RGB"), rgba.getchannel("A")
    lifted = rgb.point(lambda v: int(34 + v * 0.93))
    lifted = ImageEnhance.Contrast(lifted).enhance(1.08)
    lifted.putalpha(a)
    lifted.save(os.path.join(OUT, "mouse_dark.png"), optimize=True)
    meta = {"size": list(rgba.size),
            "hotspots": {k: [x - box[0], y - box[1]] for k, (x, y) in HOTSPOTS.items()}}
    with open(os.path.join(OUT, "mouse.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print("ok", rgba.size, meta)


if __name__ == "__main__":
    main()
