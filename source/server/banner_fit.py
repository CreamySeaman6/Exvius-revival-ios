"""Summon detail art letterboxed to the frame the stock app draws it in.

The summon detail screen draws its banner art (requested from `.../static_banner/gacha/sub/<file>`) into
a fixed frame about 3.5 times as wide as it is tall, and stretches whatever image it gets to fill it.
Many of the archived banners are 640x160 or 640x392, so on the iPhone their lettering came out squashed
(operator screenshots, 2026-11-05). The Android build fits them with a hook (source/exvius/summon_art.js);
the iPhone has none, so the server pads each such image to the frame's proportions instead, centred on a
blurred, darkened copy of itself. The list banners (`gacha/main/`) size their rows to the image and are left alone.

Results are cached in ios-cache/banner-fit/. Needs Pillow; without it, or with EXVIUS_IOS_BANNER_FIT=0,
images are served as they are.

The app keeps every banner image it has downloaded and never asks for that file again, so a phone that saw the
squashed art keeps showing it. With EXVIUS_IOS_BANNER_FIT_NAMES=1 (the iPhone server's default) the summon
tables name each detail image `<name>-fit.png`, which the phone has never downloaded; the server maps that
name back to the real file (`real_rel`) and pads it. Raise FIT_SUFFIX's number to make phones fetch again.
"""
from __future__ import annotations

import hashlib
import io
import os

FRAME = (640, 183)          # the detail frame's proportions, measured from the phone (848 x 242 points)
BASE_FRAME = (640, 392)     # the base GachaDetailScene's frame (friend-point and other layout-0 summons)
TOLERANCE = 0.06            # images already within 6% of the frame's shape are left alone
STYLE = "blur2"             # part of the cache key: change it when the padding's look changes


def _backdrop(image, canvas):
    """The padding: the art itself, scaled to cover the frame, blurred and darkened, so the sides read as
    part of the banner instead of empty bars."""
    from PIL import Image, ImageEnhance, ImageFilter
    width, height = image.size
    scale = max(canvas[0] / width, canvas[1] / height)
    cover = image.convert("RGB").resize((max(1, round(width * scale)), max(1, round(height * scale))),
                                        Image.BILINEAR)
    left, top = (cover.width - canvas[0]) // 2, (cover.height - canvas[1]) // 2
    cover = cover.crop((left, top, left + canvas[0], top + canvas[1]))
    cover = cover.filter(ImageFilter.GaussianBlur(max(4, canvas[1] // 14)))
    cover = ImageEnhance.Brightness(cover).enhance(0.45)
    return cover.convert("RGBA")


def enabled() -> bool:
    return os.environ.get("EXVIUS_IOS_BANNER_FIT", "1") == "1"


FIT_SUFFIX = "-fit1"
# Friend-point and other layout-0 summons (the Standard Summon) open `GachaDetailScene`, whose frame is
# 640x392 (BASE_FRAME), not the paid summons' 3.5:1 frame (`GachaPayDetailScene`). Padding their art to
# 3.5:1 squeezed it into the middle of that frame (operator screenshot, 2026-11-06). They get this name
# instead (one the phone hasn't cached) and are fitted to BASE_FRAME: 640x392 art is served as it is.
PLAIN_SUFFIX = "-full1"


def names_enabled() -> bool:
    return enabled() and os.environ.get("EXVIUS_IOS_BANNER_FIT_NAMES", "0") == "1"


def fit_name(name: str, pad: bool = True) -> str:
    """The detail image name the summon tables send: `x.png` -> `x-fit1.png` when renaming is on
    (`x-full1.png` for art that must not be padded)."""
    if (not name or not names_enabled() or not name.lower().endswith(".png")
            or FIT_SUFFIX + "." in name or PLAIN_SUFFIX + "." in name):
        return name
    return name[:-4] + (FIT_SUFFIX if pad else PLAIN_SUFFIX) + name[-4:]


def _sub(rel: str) -> bool:
    return "/static_banner/gacha/sub/" in "/" + rel


def is_plain(rel: str) -> bool:
    """True for a requested `.../gacha/sub/x-full1.png`: fit it to BASE_FRAME, not FRAME."""
    return _sub(rel) and rel.lower().endswith(PLAIN_SUFFIX + ".png")


def real_rel(rel: str) -> str:
    """A requested `.../gacha/sub/x-fit1.png` (or `x-full1.png`) back to the file it stands for."""
    for suffix in (FIT_SUFFIX, PLAIN_SUFFIX):
        if _sub(rel) and rel.lower().endswith(suffix + ".png"):
            return rel[:-len(suffix + ".png")] + rel[-4:]
    return rel


def wants(rel: str) -> bool:
    return enabled() and "/static_banner/gacha/sub/" in "/" + rel and rel.lower().endswith(".png")


def _cache_dir() -> str:
    try:
        import ios_art
        base = ios_art.cache_dir()
    except Exception:  # noqa: BLE001
        base = os.path.join(os.environ.get("FFBE_SERVER_ROOT", "."), "ios-cache")
    path = os.path.join(base, "banner-fit")
    os.makedirs(path, exist_ok=True)
    return path


def fit(data: bytes, frame: tuple[int, int] = FRAME) -> tuple[bytes, str | None]:
    """(bytes, note): the image padded to the frame's shape, or the input unchanged."""
    try:
        from PIL import Image
    except ImportError:
        return data, None
    key = hashlib.sha1(data + STYLE.encode() + (b"" if frame == FRAME else repr(frame).encode())).hexdigest()[:20]
    cached = os.path.join(_cache_dir(), key + ".png")
    if os.path.isfile(cached):
        with open(cached, "rb") as fh:
            return fh.read(), "letterboxed (cached)"
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:  # noqa: BLE001 -- not an image we can read: serve it as it is
        return data, None
    width, height = image.size
    target = frame[0] / frame[1]
    if width <= 0 or height <= 0 or abs(width / height - target) / target <= TOLERANCE:
        return data, None
    # Canvas at the image's own resolution: as wide as the image, or as tall, whichever keeps every pixel.
    if width / height > target:
        canvas = (width, round(width / target))
    else:
        canvas = (round(height * target), height)
    out = _backdrop(image, canvas)
    art = image.convert("RGBA")
    out.paste(art, ((canvas[0] - width) // 2, (canvas[1] - height) // 2), art)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    result = buf.getvalue()
    with open(cached, "wb") as fh:
        fh.write(result)
    return result, f"letterboxed {width}x{height} -> {canvas[0]}x{canvas[1]}"
