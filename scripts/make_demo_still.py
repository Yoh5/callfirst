"""Draw the demo's doorbell still: an illustration, not a photograph.

    python scripts/make_demo_still.py      (needs Pillow; not an app dependency)

A doorbell's-eye view of a porch with a faceless figure holding an envelope.
Drawn rather than photographed so the demo shows no real person and carries
no one else's copyright. Written to demo/default.jpg, which scripts/demo.py
hands to the emulator (--media-dir).
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 960
OUT = Path(__file__).resolve().parent.parent / "demo" / "default.jpg"


def font(size: int):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    img = Image.new("RGB", (W, H), (182, 196, 206))
    d = ImageDraw.Draw(img)

    # Street and lawn beyond the porch, then the porch floor.
    d.rectangle([0, 0, W, 300], fill=(196, 214, 226))
    d.rectangle([0, 250, W, 420], fill=(122, 150, 104))
    d.rectangle([0, 360, W, 440], fill=(150, 150, 146))
    d.polygon([(0, 560), (W, 560), (W, H), (0, H)], fill=(168, 150, 128))
    for x in range(-400, W + 400, 120):          # porch boards, converging
        d.line([(W / 2 + (x - W / 2) * 0.35, 560), (x, H)], fill=(150, 132, 112), width=4)
    d.rectangle([0, 440, W, 560], fill=(176, 160, 138))

    # Porch posts and a shrub.
    for x in (70, W - 130):
        d.rectangle([x, 120, x + 60, 700], fill=(236, 232, 224))
    d.ellipse([W - 330, 380, W - 120, 600], fill=(88, 120, 78))

    # The visitor: faceless, a dark jacket, a cap, an envelope held out.
    cx = W // 2 + 40
    d.rounded_rectangle([cx - 150, 330, cx + 150, 900], radius=90, fill=(44, 52, 66))
    d.ellipse([cx - 78, 150, cx + 78, 320], fill=(196, 160, 132))
    d.chord([cx - 88, 130, cx + 88, 260], 180, 360, fill=(36, 42, 54))
    d.rounded_rectangle([cx - 120, 186, cx + 10, 202], radius=8, fill=(36, 42, 54))  # cap brim
    d.rounded_rectangle([cx - 250, 520, cx - 60, 600], radius=30, fill=(44, 52, 66))
    d.rectangle([cx - 330, 480, cx - 200, 570], fill=(238, 232, 214))      # envelope
    d.line([(cx - 330, 480), (cx - 265, 530), (cx - 200, 480)], fill=(200, 190, 170), width=4)
    d.rounded_rectangle([cx + 60, 380, cx + 140, 470], radius=12, fill=(64, 74, 90))  # lanyard

    # A doorbell lens bends the world.
    img = barrel(img, 0.18).filter(ImageFilter.GaussianBlur(1.2))
    vignette = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vignette).ellipse([-160, -200, W + 160, H + 200], fill=255)
    img = Image.composite(img, Image.new("RGB", (W, H), (20, 20, 24)),
                          vignette.filter(ImageFilter.GaussianBlur(90)))

    d = ImageDraw.Draw(img)
    d.text((32, H - 64), "Front Door", font=font(34), fill=(255, 255, 255))
    d.text((W - 360, H - 64), "ILLUSTRATION", font=font(30), fill=(255, 255, 255))
    OUT.parent.mkdir(exist_ok=True)
    img.save(OUT, quality=88)
    print(f"wrote {OUT}")


def barrel(img: Image.Image, k: float) -> Image.Image:
    src = img.load()
    out = Image.new("RGB", img.size)
    dst = out.load()
    cx, cy = W / 2, H / 2
    norm = math.hypot(cx, cy)
    for y in range(H):
        for x in range(W):
            dx, dy = (x - cx) / norm, (y - cy) / norm
            r = dx * dx + dy * dy
            sx, sy = cx + dx * (1 + k * r) * norm, cy + dy * (1 + k * r) * norm
            if 0 <= sx < W and 0 <= sy < H:
                dst[x, y] = src[int(sx), int(sy)]
    return out


if __name__ == "__main__":
    main()
