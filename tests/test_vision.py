"""Photo color extraction — the one defensible piece of image ML (colors only)."""
import io

import pytest
from PIL import Image

import vision


def _png(color, size=(100, 100)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return b.getvalue()


def test_solid_red_detected():
    colors = vision.extract_colors(_png((205, 25, 25)))
    assert colors and colors[0]["name"] == "red" and colors[0]["pct"] > 50


def test_solid_navy_detected():
    colors = vision.extract_colors(_png((20, 30, 95)))
    assert colors[0]["name"] in ("navy", "blue")


def test_result_shape():
    c = vision.extract_colors(_png((40, 150, 60)))[0]
    assert c["name"] == "green"
    assert c["hex"].startswith("#") and len(c["hex"]) == 7
    assert 0 <= c["pct"] <= 100


def test_invalid_image_raises_valueerror():
    with pytest.raises(ValueError):
        vision.extract_colors(b"this is definitely not an image")


def test_max_colors_cap():
    img = Image.new("RGB", (120, 120))
    bands = [(200, 30, 30), (40, 80, 200), (40, 150, 60), (235, 210, 50), (120, 50, 160), (235, 130, 30)]
    px = img.load()
    for y in range(120):
        col = bands[y * len(bands) // 120]
        for x in range(120):
            px[x, y] = col
    b = io.BytesIO()
    img.save(b, "PNG")
    out = vision.extract_colors(b.getvalue(), max_colors=3)
    assert 1 <= len(out) <= 3
