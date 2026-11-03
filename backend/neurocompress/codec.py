"""Lossless image codec: neural context model + range coder + self-describing container."""
import hashlib
import os
import struct
import zlib
from dataclasses import dataclass

import numpy as np

from . import model as M
from .rangecoder import RangeDecodeError, RangeDecoder, RangeEncoder

MAGIC = b"NCZ1"
VERSION = 1
_HEAD_STRUCT = struct.Struct(">4sBBHII8s")
CHUNK = 32768


class NeuroCompressError(Exception):
    """Base error."""


class UnsupportedImageError(NeuroCompressError):
    pass


class CorruptFileError(NeuroCompressError):
    pass


class IntegrityError(NeuroCompressError):
    pass


def max_pixels() -> int:
    return int(os.environ.get("NC_MAX_PIXELS", "1048576"))


def pixel_sha256(img: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(img, dtype=np.uint8).tobytes()).hexdigest()


def _validate(img):
    if not isinstance(img, np.ndarray) or img.dtype != np.uint8:
        raise UnsupportedImageError("image must be a uint8 numpy array")
    if img.ndim == 3 and img.shape[2] == 1:
        img = img[:, :, 0]
    if img.ndim == 2:
        pass
    elif img.ndim == 3 and img.shape[2] == 3:
        pass
    else:
        raise UnsupportedImageError("only grayscale (H,W) and RGB (H,W,3) images are supported")
    h, w = img.shape[:2]
    if h < 1 or w < 1:
        raise UnsupportedImageError("empty image")
    if h * w > max_pixels():
        raise UnsupportedImageError(f"image has {h*w} pixels; limit is {max_pixels()} (NC_MAX_PIXELS)")
    return img


def _planes(img):
    if img.ndim == 2:
        return [img]
    return [img[:, :, 1], img[:, :, 0], img[:, :, 2]]  # G, R, B


def _wavefront(H, W):
    """Coding order: ascending t = x + 2y (ties by y). Pixels sharing t are mutually independent."""
    ys, xs = np.divmod(np.arange(H * W), W)
    t = xs + 2 * ys
    order = np.lexsort((ys, t))
    ys, xs, t = ys[order], xs[order], t[order]
    bounds = np.concatenate(([0], np.cumsum(np.bincount(t, minlength=W + 2 * H - 2))))
    return ys, xs, bounds


@dataclass
class ArtifactInfo:
    width: int
    height: int
    channels: int
    model_name: str
    model_id: str
    sha256: str
    payload_bytes: int
    total_bytes: int


# ---------------------------------------------------------------- container
def _pack(img_shape, model, sha, payload):
    h, w = img_shape[:2]
    ch = 1 if len(img_shape) == 2 else 3
    name = model.name.encode()
    body = _HEAD_STRUCT.pack(MAGIC, VERSION, ch, 0, w, h, model.model_id)
    body += bytes([len(name)]) + name + bytes.fromhex(sha) + struct.pack(">I", len(payload)) + payload
    return body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _parse(blob: bytes):
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < _HEAD_STRUCT.size + 1 + 32 + 4 + 4:
        raise CorruptFileError("file too small to be a NeuroCompress artifact")
    if blob[:4] != MAGIC:
        raise CorruptFileError("not a NeuroCompress file (bad magic number)")
    if struct.unpack(">I", blob[-4:])[0] != (zlib.crc32(blob[:-4]) & 0xFFFFFFFF):
        raise CorruptFileError("CRC32 mismatch: file is corrupted or truncated")
    _, ver, ch, _, w, h, mid = _HEAD_STRUCT.unpack_from(blob, 0)
    if ver != VERSION:
        raise CorruptFileError(f"unsupported container version {ver}")
    if ch not in (1, 3) or w < 1 or h < 1 or w * h > max_pixels():
        raise CorruptFileError("invalid or oversized image dimensions in header")
    pos = _HEAD_STRUCT.size
    nlen = blob[pos]
    pos += 1
    name = bytes(blob[pos:pos + nlen]).decode("ascii", "replace")
    pos += nlen
    sha = bytes(blob[pos:pos + 32]).hex()
    pos += 32
    plen = struct.unpack_from(">I", blob, pos)[0]
    pos += 4
    if pos + plen + 4 != len(blob):
        raise CorruptFileError("payload length does not match file size")
    return dict(w=w, h=h, ch=ch, name=name, model_id=bytes(mid), sha=sha, payload=bytes(blob[pos:pos + plen]))


def inspect_artifact(blob: bytes) -> ArtifactInfo:
    p = _parse(blob)
    return ArtifactInfo(p["w"], p["h"], p["ch"], p["name"], p["model_id"].hex(), p["sha"],
                        len(p["payload"]), len(blob))


# ---------------------------------------------------------------- compress / decompress
def compress(img: np.ndarray, model_name: str = "base", progress=None) -> bytes:
    img = _validate(img)
    model = M.get_model(model_name)
    rows, _ = M.get_tables()
    H, W = img.shape[:2]
    planes = _planes(img)
    ys_all, xs_all, _ = _wavefront(H, W)
    enc = RangeEncoder()
    refP, R = None, []
    total = len(planes) * H * W
    done = 0
    for c, plane in enumerate(planes):
        P = M.pad_plane(plane)
        if c > 0:
            refP = P0
        for a in range(0, H * W, CHUNK):
            ys, xs = ys_all[a:a + CHUNK], xs_all[a:a + CHUNK]
            X, base = M.build_features(P, ys, xs, c, refP, R[c - 1] if c else None, R[0] if c else None)
            mq, k = model.predict(X)
            s = (plane[ys, xs].astype(np.int64) - base) & 255
            u = (s - (mq >> 2)) & 255
            enc.encode_many(rows, (k * 4 + (mq & 3)).tolist(), u.tolist())
            done += len(ys)
            if progress:
                progress(done / total, f"encoding plane {c + 1}/{len(planes)}")
        R.append(M.residual_plane(plane))
        if c == 0:
            P0 = P
    return _pack(img.shape, model, pixel_sha256(img), enc.finish())


def decompress(blob: bytes, progress=None, verify: bool = True):
    p = _parse(blob)
    H, W, C = p["h"], p["w"], p["ch"]
    try:
        model = M.get_model(p["name"])
    except FileNotFoundError as e:
        raise CorruptFileError(f"model '{p['name']}' referenced by file is not installed") from e
    if model.model_id != p["model_id"]:
        raise CorruptFileError("model weights differ from those used for compression (model id mismatch)")
    rows, _ = M.get_tables()
    ys_all, xs_all, bounds = _wavefront(H, W)
    dec = RangeDecoder(p["payload"])
    planes, R = [], []
    refP = None
    steps = len(bounds) - 1
    try:
        for c in range(C):
            P = M.pad_plane(np.zeros((H, W), dtype=np.int32))
            if c > 0:
                refP = M.pad_plane(planes[0])
            for t in range(steps):
                a, b = int(bounds[t]), int(bounds[t + 1])
                if a == b:
                    continue
                ys, xs = ys_all[a:b], xs_all[a:b]
                X, base = M.build_features(P, ys, xs, c, refP, R[c - 1] if c else None, R[0] if c else None)
                mq, k = model.predict(X)
                u = np.asarray(dec.decode_many(rows, (k * 4 + (mq & 3)).tolist()), dtype=np.int64)
                P[ys + 2, xs + 2] = (base + ((u + (mq >> 2)) & 255)) & 255
                if progress and (t % 16 == 0 or t == steps - 1):
                    progress((c * steps + t + 1) / (C * steps), f"decoding plane {c + 1}/{C}")
            plane = P[2:, 2:W + 2].copy()
            planes.append(plane)
            R.append(M.residual_plane(plane))
    except RangeDecodeError as e:
        raise CorruptFileError(str(e)) from e
    if C == 1:
        img = planes[0].astype(np.uint8)
    else:
        img = np.stack([planes[1], planes[0], planes[2]], axis=-1).astype(np.uint8)
    digest = pixel_sha256(img)
    if verify and digest != p["sha"]:
        raise IntegrityError("decoded pixels do not match the SHA-256 stored in the file")
    return img, ArtifactInfo(W, H, C, p["name"], p["model_id"].hex(), p["sha"], len(p["payload"]), len(blob))
