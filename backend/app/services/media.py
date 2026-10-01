"""Listing photos: re-encode (strips EXIF/GPS), thumbnail, blur detection (edge variance),
perceptual-hash duplicate detection; and the listing completeness/quality score."""

import io
import uuid

from fastapi import HTTPException
from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from ..config import settings
from ..models import Property, PropertyMedia
from ..security import utcnow
from ..storage import get_storage

ALLOWED = {"image/jpeg", "image/png", "image/webp"}
BLUR_THRESHOLD = 60.0
DUP_DISTANCE = 6
Image.MAX_IMAGE_PIXELS = 40_000_000


def dhash(img: Image.Image) -> str:
    g = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = list(g.tobytes())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


_LAPLACIAN = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128)


def blur_score(img: Image.Image) -> float:
    """Variance of the Laplacian on a 640 px-wide grayscale copy, ignoring an 8 px border.
    Calibrated in tests/test_units.py: sharp photos score well above 60, out-of-focus ones below 45."""
    g = img.convert("L")
    w = 640
    g = g.resize((w, max(1, int(g.height * w / g.width))), Image.Resampling.BILINEAR)
    if g.width > 32 and g.height > 32:
        g = g.crop((8, 8, g.width - 8, g.height - 8))
    return float(ImageStat.Stat(g.filter(_LAPLACIAN)).var[0])


def process_upload(prop: Property, data: bytes, content_type: str, existing: list[PropertyMedia]) -> PropertyMedia:
    if content_type not in ALLOWED:
        raise HTTPException(415, "Upload a JPG, PNG or WebP photo.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Photos must be under {settings.max_upload_mb} MB.")
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "That file isn't a readable photo.")
    if min(img.size) < 320:
        raise HTTPException(422, "Photo is too small. Use at least 320 px on the short side.")
    img.thumbnail((2000, 2000))
    score = blur_score(img)
    ph = dhash(img)
    duplicate = any(hamming(ph, m.phash) <= DUP_DISTANCE for m in existing)

    full, thumb = io.BytesIO(), io.BytesIO()
    img.save(full, "WEBP", quality=82, method=4)
    t = img.copy()
    t.thumbnail((640, 640))
    t.save(thumb, "WEBP", quality=76, method=4)
    mid = uuid.uuid4()
    key = f"properties/{prop.id}/{mid}.webp"
    thumb_key = f"properties/{prop.id}/{mid}_t.webp"
    storage = get_storage()
    storage.save(key, full.getvalue(), "image/webp")
    storage.save(thumb_key, thumb.getvalue(), "image/webp")
    return PropertyMedia(id=mid, property_id=prop.id, storage_key=key, thumb_key=thumb_key, width=img.width,
                         height=img.height, size_bytes=len(full.getvalue()), phash=ph, blur_score=round(score, 1),
                         is_blurry=score < BLUR_THRESHOLD, is_duplicate=duplicate,
                         sort_order=(max((m.sort_order for m in existing), default=-1) + 1))


def good_photos(prop: Property) -> int:
    return sum(1 for m in prop.media if not m.is_duplicate)


def evaluate_quality(prop: Property) -> None:
    flags: list[str] = []
    media = prop.media
    clear = [m for m in media if not m.is_duplicate and not m.is_blurry]
    blurry = sum(1 for m in media if m.is_blurry and not m.is_duplicate)
    dups = sum(1 for m in media if m.is_duplicate)
    score = min(len(clear), 5) / 5 * 35
    if good_photos(prop) < 3:
        flags.append(f"Add {3 - good_photos(prop)} more photo{'s' if 3 - good_photos(prop) > 1 else ''} (3 minimum)")
    if blurry:
        flags.append(f"{blurry} photo{'s look' if blurry > 1 else ' looks'} blurry. Retake in daylight for more interest")
    if dups:
        flags.append(f"{dups} duplicate photo{'s' if dups > 1 else ''} won't be counted")
    if prop.lat is not None and prop.lng is not None:
        score += 15
    else:
        flags.append("Drop a pin on the map")
    if prop.type and prop.size_sqft:
        score += 15
    else:
        flags.append("Add the size")
    if prop.price_amount or prop.price_negotiable:
        score += 10
    else:
        flags.append("Add a price or choose 'open to discuss'")
    if prop.availability == "now" or prop.available_from:
        score += 5
    if prop.description and len(prop.description.strip()) >= 40:
        score += 10
    else:
        flags.append("Add a short description (40+ characters)")
    if prop.amenities:
        score += 5
    if prop.address:
        score += 5
    prop.quality_score = round(score)
    prop.quality_flags = flags


def publish_blockers(prop: Property) -> list[str]:
    missing = []
    if prop.lat is None or prop.lng is None:
        missing.append("location")
    if not prop.size_sqft:
        missing.append("size")
    if good_photos(prop) < 3:
        missing.append("3 photos")
    if not (prop.price_amount or prop.price_negotiable):
        missing.append("price or 'open to discuss'")
    if prop.availability == "future" and not prop.available_from:
        missing.append("available-from date")
    return missing


def is_recently_updated(prop: Property) -> bool:
    return bool(prop.last_confirmed_at and (utcnow() - prop.last_confirmed_at).days <= 14)
