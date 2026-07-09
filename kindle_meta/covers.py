"""Cover-Bilder für die Kindle-Anzeige optimieren.

Amazon empfiehlt für Cover ein Seitenverhältnis von etwa **1,6 : 1**
(Höhe : Breite) und eine Höhe im Bereich von ~2560 px. Diese Funktionen
skalieren (und schneiden optional zu), konvertieren nach RGB-JPEG und
komprimieren – damit das Cover auf dem Paperwhite scharf und im richtigen
Format erscheint, ohne die Datei unnötig aufzublähen.

Benötigt Pillow. Ist es nicht installiert, löst ``optimize_for_kindle``
``CoverError`` aus; der Rest der App funktioniert weiterhin.
"""

from __future__ import annotations

import io

# Kindle-freundliche Zielwerte.
TARGET_RATIO = 1.6          # Höhe / Breite
TARGET_HEIGHT = 1680        # px – scharf auf dem Paperwhite, moderate Dateigröße
JPEG_QUALITY = 85


class CoverError(Exception):
    pass


def available() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def optimize_for_kindle(
    data: bytes,
    *,
    target_height: int = TARGET_HEIGHT,
    crop_to_ratio: bool = False,
    quality: int = JPEG_QUALITY,
) -> tuple[bytes, str]:
    """Optimiert Cover-Bilddaten für Kindle und gibt ``(bytes, mime)`` zurück.

    - Konvertiert nach RGB (Kindle-Cover sind JPEG).
    - ``crop_to_ratio=True`` schneidet mittig auf das 1,6:1-Verhältnis zu,
      sonst bleibt das Originalverhältnis erhalten (nur skaliert).
    - Skaliert auf ``target_height`` (nur verkleinern, nie hochskalieren).
    """
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - abhängig von Umgebung
        raise CoverError(
            "Pillow ist nicht installiert (pip install Pillow), "
            "Cover-Optimierung nicht möglich."
        ) from exc

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise CoverError(f"Cover-Bild konnte nicht gelesen werden: {exc}") from exc

    if img.mode != "RGB":
        # Transparenz auf weißen Hintergrund legen, sonst direkt konvertieren.
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")

    if crop_to_ratio:
        img = _center_crop_to_ratio(img, TARGET_RATIO)

    # Nur verkleinern – Hochskalieren würde Qualität vortäuschen.
    if img.height > target_height:
        new_w = round(img.width * target_height / img.height)
        img = img.resize((new_w, target_height), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue(), "image/jpeg"


def _center_crop_to_ratio(img, ratio: float):
    """Schneidet mittig auf Höhe/Breite == ``ratio`` zu."""
    w, h = img.width, img.height
    current = h / w
    if abs(current - ratio) < 0.01:
        return img
    if current > ratio:
        # zu hoch -> Höhe beschneiden
        new_h = round(w * ratio)
        top = (h - new_h) // 2
        return img.crop((0, top, w, top + new_h))
    # zu breit -> Breite beschneiden
    new_w = round(h / ratio)
    left = (w - new_w) // 2
    return img.crop((left, 0, left + new_w, h))


def rotate(data: bytes, degrees: int, *, quality: int = JPEG_QUALITY) -> tuple[bytes, str]:
    """Dreht ein Cover um ein Vielfaches von 90° (im Uhrzeigersinn) → JPEG."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise CoverError("Pillow ist nicht installiert.") from exc
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise CoverError(f"Cover-Bild konnte nicht gelesen werden: {exc}") from exc
    # Pillow dreht gegen den Uhrzeigersinn -> negieren für „im Uhrzeigersinn".
    img = img.convert("RGB").rotate(-degrees, expand=True)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue(), "image/jpeg"


def crop(
    data: bytes, box: tuple[int, int, int, int], *, quality: int = JPEG_QUALITY
) -> tuple[bytes, str]:
    """Schneidet auf ``box`` (left, top, right, bottom) zu → JPEG."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise CoverError("Pillow ist nicht installiert.") from exc
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise CoverError(f"Cover-Bild konnte nicht gelesen werden: {exc}") from exc
    left, top, right, bottom = box
    if right <= left or bottom <= top:
        raise CoverError("Ungültiger Zuschnitt-Bereich.")
    img = img.convert("RGB").crop((left, top, right, bottom))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue(), "image/jpeg"


def thumbnail(data: bytes, *, max_side: int = 200, quality: int = 80) -> tuple[bytes, str]:
    """Erzeugt ein kleines Vorschaubild (für die Bibliotheks-Ansicht) → JPEG."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise CoverError("Pillow ist nicht installiert.") from exc
    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue(), "image/jpeg"


def optimize_metadata_cover(meta, **kwargs) -> None:
    """Optimiert das Cover eines ``BookMetadata`` in-place, falls vorhanden."""
    if getattr(meta, "cover", None):
        meta.cover, meta.cover_mime = optimize_for_kindle(meta.cover, **kwargs)
