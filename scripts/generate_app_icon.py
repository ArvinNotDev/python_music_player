"""Generate the Windows multi-resolution ICO companion for the SVG app icon."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ICO_PATH = ROOT / "assets" / "rw_player.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_icon(size: int = 256) -> Image.Image:
    """Draw the RW Player record mark at full resolution with transparent corners."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Dark violet-to-charcoal rounded-square background.
    for y in range(8, 248):
        t = (y - 8) / 240
        start = (36, 32, 68)
        end = (16, 19, 29)
        color = tuple(round(start[i] + (end[i] - start[i]) * t) for i in range(3))
        draw.line((8, y, 248, y), fill=(*color, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8, 8, 248, 248), radius=58, fill=255)
    image.putalpha(mask)
    draw = ImageDraw.Draw(image)

    # Vinyl disc and restrained grooves.
    disc = Image.new("RGBA", (172, 172), (0, 0, 0, 0))
    disc_draw = ImageDraw.Draw(disc)
    for y in range(172):
        t = y / 171
        start = (181, 169, 255)
        end = (73, 61, 208)
        color = tuple(round(start[i] + (end[i] - start[i]) * t) for i in range(3))
        disc_draw.line((0, y, 171, y), fill=(*color, 255))
    disc_mask = Image.new("L", (172, 172), 0)
    ImageDraw.Draw(disc_mask).ellipse((0, 0, 171, 171), fill=255)
    disc.putalpha(disc_mask)
    image.alpha_composite(disc, (42, 38))
    draw = ImageDraw.Draw(image)
    for radius, alpha in ((73, 48), (61, 40), (49, 34), (38, 28)):
        draw.ellipse(
            (128 - radius, 124 - radius, 128 + radius, 124 + radius),
            outline=(255, 255, 255, alpha),
            width=2,
        )

    # Pale center label and RW wordmark.
    draw.ellipse((97, 93, 159, 155), fill=(231, 226, 255, 255))
    draw.text((128, 124), "RW", font=_font(29), fill=(48, 38, 95, 255), anchor="mm")

    # Small play badge.
    draw.arc((140, 35, 230, 125), start=215, end=300, fill=(255, 255, 255, 105), width=3)
    draw.ellipse((183, 37, 219, 73), fill=(93, 203, 218, 255))
    draw.polygon(((196, 45), (209, 55), (196, 65)), fill=(17, 33, 43, 255))

    draw.rounded_rectangle((8, 8, 248, 248), radius=58, outline=(255, 255, 255, 26), width=2)
    return image


def main() -> int:
    image = render_icon()
    image.save(ICO_PATH, format="ICO", sizes=SIZES)
    if not ICO_PATH.is_file() or ICO_PATH.stat().st_size == 0:
        raise RuntimeError("Windows application icon was not generated.")
    print(f"Generated {ICO_PATH} ({ICO_PATH.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
