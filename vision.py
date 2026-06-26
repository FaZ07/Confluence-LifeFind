"""
LifeFind — photo color analysis.

The ONE defensible piece of image ML: extract the dominant clothing colors from an
uploaded photo (unsupervised median-cut color clustering) and map them to named
colors, so a searcher can drop a photo and have "red, blue, white" flow straight
into the lead scoring.

Deliberately NOT here: face recognition, age/gender estimation, identity matching.
Inferring a person's age or gender from a single photo is bias-prone pseudo-science
and exactly the kind of overclaim that discredits a serious system. We only read
colors, the image is processed in memory and never stored, and the result is always
presented as "detected — review before using".
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps

# Guard against decompression-bomb uploads — images whose declared dimensions are
# huge but compress tiny, designed to exhaust memory on decode. Pillow raises
# Image.DecompressionBombError past this cap, which extract_colors turns into a 422.
Image.MAX_IMAGE_PIXELS = 40_000_000  # ~40 MP

# Representative RGB for common clothing colours (grey absorbs "gray").
NAMED: dict[str, tuple[int, int, int]] = {
    "red": (200, 30, 30), "maroon": (110, 20, 30), "pink": (240, 140, 170),
    "orange": (235, 130, 30), "yellow": (235, 210, 50), "gold": (200, 160, 40),
    "green": (40, 140, 60), "olive": (110, 110, 40), "teal": (30, 140, 140),
    "blue": (40, 80, 200), "navy": (20, 30, 90), "purple": (120, 50, 160),
    "brown": (110, 70, 40), "tan": (200, 170, 120), "beige": (225, 210, 180),
    "cream": (245, 240, 220), "white": (245, 245, 245), "grey": (140, 140, 140),
    "silver": (190, 190, 195), "black": (25, 25, 25),
}


def _nearest_name(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    best, best_d = "grey", 1e18
    for name, (nr, ng, nb) in NAMED.items():
        d = (r - nr) ** 2 + (g - ng) ** 2 + (b - nb) ** 2
        if d < best_d:
            best, best_d = name, d
    return best


def extract_colors(data: bytes, max_colors: int = 5, k: int = 8) -> list[dict]:
    """Return the dominant named colors in a photo, ordered by coverage:
    [{"name", "hex", "pct"}]. Raises ValueError on an unreadable image."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise ValueError("unreadable image") from e

    # Centre-weight: sample a central band (torso-ish) to cut background influence.
    # This is an unbiased geometric crop — no skin/face/identity heuristics.
    w, h = img.size
    left, right = int(w * 0.20), int(w * 0.80)
    top, bottom = int(h * 0.20), int(h * 0.90)
    if right > left and bottom > top:
        img = img.crop((left, top, right, bottom))
    img = img.resize((128, 128))

    pal = img.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    palette = pal.getpalette() or []
    counts = pal.getcolors() or []
    total = sum(c for c, _ in counts) or 1

    agg: dict[str, dict] = {}
    for count, idx in counts:
        rgb = (palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2])
        name = _nearest_name(rgb)
        e = agg.setdefault(name, {"count": 0, "rgb": rgb, "best": 0})
        e["count"] += count
        if count > e["best"]:
            e["best"], e["rgb"] = count, rgb

    out = [{"name": n, "hex": "#%02x%02x%02x" % e["rgb"], "pct": round(100 * e["count"] / total)}
           for n, e in agg.items()]
    out.sort(key=lambda c: -c["pct"])
    return out[:max_colors]
