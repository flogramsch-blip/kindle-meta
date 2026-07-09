"""Tests für die Cover-Optimierung."""

import io

import pytest

from kindle_meta import covers


def _make_png(width: int, height: int) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (width, height), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_optimize_scales_down_and_makes_jpeg():
    from PIL import Image

    data = _make_png(2000, 3000)  # sehr groß
    out, mime = covers.optimize_for_kindle(data, target_height=1680)
    assert mime == "image/jpeg"
    img = Image.open(io.BytesIO(out))
    assert img.height == 1680
    assert img.format == "JPEG"
    # Seitenverhältnis bleibt erhalten (kein Crop).
    assert abs(img.width / img.height - 2000 / 3000) < 0.01


def test_optimize_does_not_upscale():
    from PIL import Image

    data = _make_png(400, 600)
    out, _ = covers.optimize_for_kindle(data, target_height=1680)
    img = Image.open(io.BytesIO(out))
    assert img.height == 600  # nicht hochskaliert


def test_crop_to_ratio():
    from PIL import Image

    data = _make_png(1000, 3000)  # zu hoch
    out, _ = covers.optimize_for_kindle(data, target_height=1600, crop_to_ratio=True)
    img = Image.open(io.BytesIO(out))
    assert abs(img.height / img.width - covers.TARGET_RATIO) < 0.02


def test_invalid_image_raises():
    with pytest.raises(covers.CoverError):
        covers.optimize_for_kindle(b"not an image")


def test_available_is_bool():
    assert isinstance(covers.available(), bool)


def test_rotate_swaps_dimensions():
    from PIL import Image

    data = _make_png(400, 600)
    out, mime = covers.rotate(data, 90)
    assert mime == "image/jpeg"
    img = Image.open(io.BytesIO(out))
    assert (img.width, img.height) == (600, 400)


def test_crop_region():
    from PIL import Image

    data = _make_png(400, 600)
    out, _ = covers.crop(data, (0, 0, 200, 300))
    img = Image.open(io.BytesIO(out))
    assert (img.width, img.height) == (200, 300)


def test_crop_invalid_box_raises():
    data = _make_png(400, 600)
    with pytest.raises(covers.CoverError):
        covers.crop(data, (100, 100, 50, 50))


def test_thumbnail_fits_box():
    from PIL import Image

    data = _make_png(1000, 1600)
    out, _ = covers.thumbnail(data, max_side=200)
    img = Image.open(io.BytesIO(out))
    assert max(img.width, img.height) == 200
