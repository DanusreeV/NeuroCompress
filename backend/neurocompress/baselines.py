"""Conventional lossless codecs used for comparison (Pillow)."""
import io
import time

import numpy as np
from PIL import Image


def _pil(img):
    return Image.fromarray(img if img.ndim == 2 else np.ascontiguousarray(img))


def png_size(img):
    buf = io.BytesIO()
    _pil(img).save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.tell()


def webp_size(img):
    """Lossless WebP size, or None if this Pillow build lacks WebP."""
    try:
        buf = io.BytesIO()
        im = _pil(img)
        if im.mode == "L":
            im = im.convert("RGB")  # WebP stores RGB(A); gray is expanded
        im.save(buf, format="WEBP", lossless=True, quality=100, method=6)
        return buf.tell()
    except Exception:
        return None


def compare(img):
    out = {}
    for name, fn in (("png", png_size), ("webp", webp_size)):
        t = time.perf_counter()
        size = fn(img)
        out[name] = {"bytes": size, "encode_ms": round((time.perf_counter() - t) * 1000, 1)} if size else None
    return out
