"""Vyrobí ikonu aplikace assets/app.ico (+ app.png 256 px). Spuštění: python tools/make_icon.py"""
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
N = 1024


def gradient(size, c1, c2):
    g = Image.new("RGB", (size, size))
    px = g.load()
    for y in range(size):
        for x in range(size):
            f = (x + y) / (2 * size - 2)
            px[x, y] = tuple(int(a + (b - a) * f) for a, b in zip(c1, c2))
    return g


def spline(pts, steps=24):
    """Uzavřená Catmull-Rom křivka -> body polygonu."""
    out, n = [], len(pts)
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    return out


def make():
    # podklad
    bg = gradient(N, (88, 166, 255), (30, 84, 200)).convert("RGBA")
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle((24, 24, N - 24, N - 24), radius=230, fill=255)
    icon = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    icon.paste(bg, (0, 0), mask)
    # myš (vrstva, kterou pak natočíme)
    m = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(m)
    white, blue, light = (255, 255, 255, 255), (36, 96, 214, 255), (170, 205, 252, 255)
    outline = [(520, 188), (612, 204), (670, 280), (692, 400), (702, 540), (698, 680), (666, 790),
               (592, 846), (500, 858), (418, 842), (356, 800), (326, 730), (336, 648), (372, 560),
               (388, 440), (400, 300), (442, 214)]
    d.polygon(spline(outline), fill=white)                               # tělo s palcovou opěrkou
    d.line((526, 206, 526, 392), fill=blue, width=14)                    # dělení tlačítek
    d.rounded_rectangle((500, 252, 552, 352), radius=26, fill=blue)      # kolečko
    d.rounded_rectangle((334, 448, 424, 532), radius=24, fill=blue)      # palcové kolečko
    for i in range(3):
        x = 360 + i * 22
        d.line((x, 458, x, 522), fill=(110, 160, 240, 255), width=7)
    d.rounded_rectangle((334, 552, 418, 592), radius=20, fill=light)     # boční tlačítka
    d.rounded_rectangle((334, 606, 418, 646), radius=20, fill=light)
    m = m.rotate(-12, resample=Image.BICUBIC, center=(N / 2, N / 2), translate=(6, 0))

    shadow = Image.new("RGBA", (N, N), (8, 30, 90, 0))
    shadow.putalpha(m.getchannel("A").point(lambda v: v * 0.45).filter(ImageFilter.GaussianBlur(26)))
    icon.alpha_composite(shadow, (14, 30))
    icon.alpha_composite(m)

    os.makedirs(OUT, exist_ok=True)
    big = icon.resize((256, 256), Image.LANCZOS)
    big.save(os.path.join(OUT, "app.png"))
    sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
    big.save(os.path.join(OUT, "app.ico"), sizes=[(s, s) for s in sizes])
    icon.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "app_512.png"))
    print("ok")


if __name__ == "__main__":
    make()
