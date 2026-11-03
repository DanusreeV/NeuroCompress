"""Application logic: uploads, compression, decompression, benchmarking, cleanup."""
import io
import os
import re
import threading
import time
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

import neurocompress as nc
from neurocompress import baselines
from neurocompress import model as M
from neurocompress import samples as S

from . import config
from .db import Database

Image.MAX_IMAGE_PIXELS = 60_000_000  # Pillow decompression-bomb guard (we enforce a far lower limit below)
db = Database(config.DATA_DIR / "neurocompress.sqlite3")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# ------------------------------------------------------------------ helpers
class PeakMemory:
    """Samples process RSS in a thread (needs psutil; otherwise values are None)."""

    def __enter__(self):
        self.peak = self.base = None
        self._stop = threading.Event()
        try:
            import psutil
            self._proc = psutil.Process()
            self.base = self.peak = self._proc.memory_info().rss
            self._t = threading.Thread(target=self._run, daemon=True)
            self._t.start()
        except Exception:  # psutil missing or unsupported
            self._proc = None
        return self

    def _run(self):
        while not self._stop.wait(0.02):
            try:
                self.peak = max(self.peak, self._proc.memory_info().rss)
            except Exception:
                return

    def __exit__(self, *a):
        self._stop.set()
        if self._proc is not None:
            self._t.join(timeout=1)

    @property
    def peak_mb(self):
        return None if self.peak is None else round(self.peak / 2 ** 20, 1)

    @property
    def delta_mb(self):
        return None if self.peak is None else round(max(0, self.peak - self.base) / 2 ** 20, 1)


def _safe_name(name):
    name = os.path.basename(name or "image")
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:80] or "image"


def _image_path(image_id):
    return config.DATA_DIR / "images" / f"{image_id}.png"


def load_array(image_id):
    rec = db.get_image(image_id)
    if not rec or not Path(rec["path"]).is_file():
        raise ApiError(404, f"image '{image_id}' not found (it may have expired; upload it again)")
    with Image.open(rec["path"]) as im:
        arr = np.asarray(im)
    return rec, np.ascontiguousarray(arr)


def normalise_image(im):
    """Return (uint8 array, note). Only L and RGB are coded; other modes are converted (and flagged)."""
    note = None
    if im.mode == "L":
        return np.asarray(im, dtype=np.uint8), note
    if im.mode == "RGB":
        return np.asarray(im, dtype=np.uint8), note
    note = f"converted from {im.mode}"
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        note += " (alpha channel discarded)"
        im = im.convert("RGBA")
        return np.asarray(im.convert("RGB"), dtype=np.uint8), note
    if im.mode in ("1", "I;16", "I", "F"):
        if im.mode in ("I;16", "I", "F"):
            note += " (reduced to 8 bit)"
        return np.asarray(im.convert("L"), dtype=np.uint8), note
    return np.asarray(im.convert("RGB"), dtype=np.uint8), note


def register_array(arr, name, file_bytes, note=None, image_id=None):
    image_id = image_id or uuid.uuid4().hex[:12]
    path = _image_path(image_id)
    Image.fromarray(arr).save(path, format="PNG", compress_level=6)
    rec = dict(id=image_id, name=_safe_name(name), width=int(arr.shape[1]), height=int(arr.shape[0]),
               channels=1 if arr.ndim == 2 else 3, file_bytes=int(file_bytes), raw_bytes=int(arr.size),
               sha256=nc.pixel_sha256(arr), path=str(path), normalized_from=note)
    db.add_image(rec)
    return rec


def ingest_upload(data: bytes, filename: str):
    if not data:
        raise ApiError(400, "empty file")
    if len(data) > config.MAX_UPLOAD_MB * 2 ** 20:
        raise ApiError(413, f"file larger than {config.MAX_UPLOAD_MB:g} MB")
    try:
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            if w * h > config.MAX_PIXELS:
                raise ApiError(413, f"image is {w}x{h} ({w * h:,} px); this demo limits images to "
                                    f"{config.MAX_PIXELS:,} px (about {int(config.MAX_PIXELS ** 0.5)}x"
                                    f"{int(config.MAX_PIXELS ** 0.5)}). Resize it or raise NC_MAX_PIXELS.")
            im.load()
            arr, note = normalise_image(im)
    except ApiError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as e:
        raise ApiError(400, f"not a readable image file ({type(e).__name__}: {e})")
    return register_array(arr, filename, len(data), note)


def list_samples():
    config.SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    if not any(config.SAMPLES_DIR.glob("*.png")):  # first run without shipped samples: generate synthetic ones
        for name, gen in S.GENERATORS.items():
            Image.fromarray(gen()).save(config.SAMPLES_DIR / f"{name}.png")
    out = []
    for p in sorted(config.SAMPLES_DIR.glob("*.png")):
        with Image.open(p) as im:
            out.append({"name": p.stem, "width": im.width, "height": im.height,
                        "channels": 1 if im.mode == "L" else 3, "file_bytes": p.stat().st_size})
    return out


def sample_path(name):
    for s in list_samples():
        if s["name"] == name:
            return config.SAMPLES_DIR / f"{name}.png"
    raise ApiError(404, f"unknown sample '{name}'")


def resolve_image(spec):
    """spec: {'image_id': ...} or {'sample': ...} -> (record, array)"""
    if spec.get("image_id"):
        return load_array(spec["image_id"])
    if spec.get("sample"):
        iid = "sample-" + re.sub(r"[^A-Za-z0-9_-]", "", spec["sample"])
        if not db.get_image(iid) or not Path(db.get_image(iid)["path"]).is_file():
            p = sample_path(spec["sample"])
            with Image.open(p) as im:
                arr, note = normalise_image(im)
            register_array(arr, p.name, p.stat().st_size, note, image_id=iid)
        return load_array(iid)
    raise ApiError(400, "specify image_id or sample")


def check_model(name):
    if name not in M.available_models():
        raise ApiError(400, f"unknown or missing model '{name}'. Available: {M.available_models()}")
    return M.get_model(name)


# ------------------------------------------------------------------ core operations
def run_compress(arr, rec, model_name, verify=True, compare=True, progress=None, run_id=None, kind="compress",
                 baseline_cache=None):
    model = check_model(model_name)
    prog = progress or (lambda f, m=None: None)
    with PeakMemory() as mem:
        t0 = time.perf_counter()
        blob = nc.compress(arr, model_name, progress=lambda f, m=None: prog(0.05 + 0.5 * f, m))
        enc_ms = (time.perf_counter() - t0) * 1000
        info = nc.inspect_artifact(blob)
        dec_ms = pixel_equal = verified = None
        if verify:
            t1 = time.perf_counter()
            out, _ = nc.decompress(blob, progress=lambda f, m=None: prog(0.55 + 0.35 * f, "verifying: " + (m or "")))
            dec_ms = (time.perf_counter() - t1) * 1000
            pixel_equal = bool(out.shape == arr.shape and np.array_equal(out, arr))
            verified = pixel_equal and nc.pixel_sha256(out) == info.sha256
    base = {}
    if compare:
        prog(0.92, "running PNG / WebP baselines")
        if baseline_cache is not None and rec["id"] in baseline_cache:
            base = baseline_cache[rec["id"]]
        else:
            base = baselines.compare(arr)
            if baseline_cache is not None:
                baseline_cache[rec["id"]] = base
    raw = int(arr.size)
    art = len(blob)
    eff = art + model.weights_bytes
    n_samples = raw
    aid = uuid.uuid4().hex[:12]
    apath = config.DATA_DIR / "artifacts" / f"{aid}.ncz"
    apath.write_bytes(blob)
    db.add_artifact(dict(id=aid, path=str(apath), bytes=art, image_id=rec["id"], image_name=rec["name"],
                         model=model_name, sha256=info.sha256))
    png_b = (base.get("png") or {}).get("bytes")
    webp_b = (base.get("webp") or {}).get("bytes")
    sizes = dict(original_file_bytes=rec["file_bytes"], raw_bytes=raw, artifact_bytes=art,
                 payload_bytes=info.payload_bytes, header_bytes=art - info.payload_bytes,
                 model_bytes=model.weights_bytes, effective_bytes=eff)
    result = {
        "artifact_id": aid, "image": {k: rec[k] for k in ("id", "name", "width", "height", "channels",
                                                          "normalized_from")},
        "model": {"name": model_name, "params": model.params, "weights_bytes": model.weights_bytes,
                  "hidden": list(model.hidden), "model_id": model.sha256[:16]},
        "sizes": sizes,
        "ratio": raw / art, "ratio_effective": raw / eff, "reduction_pct": 100 * (1 - art / raw),
        "ratio_vs_original_file": rec["file_bytes"] / art,
        "bpsp": 8 * art / n_samples,
        "timing": {"encode_ms": round(enc_ms, 1), "decode_ms": None if dec_ms is None else round(dec_ms, 1)},
        "verification": {"performed": bool(verify), "pixel_equal": pixel_equal, "sha256_match": verified,
                         "sha256": info.sha256},
        "memory": {"peak_rss_mb": mem.peak_mb, "delta_rss_mb": mem.delta_mb,
                   "model_weights_bytes": model.weights_bytes},
        "baselines": base,
    }
    eid = db.add_experiment(
        kind=kind, run_id=run_id, image_id=rec["id"], image_name=rec["name"], model=model_name,
        width=rec["width"], height=rec["height"], channels=rec["channels"],
        original_bytes=rec["file_bytes"], raw_bytes=raw, artifact_bytes=art, payload_bytes=info.payload_bytes,
        model_bytes=model.weights_bytes, effective_bytes=eff, ratio=result["ratio"],
        ratio_effective=result["ratio_effective"], reduction_pct=result["reduction_pct"], bpsp=result["bpsp"],
        png_bytes=png_b, webp_bytes=webp_b, enc_ms=enc_ms, dec_ms=dec_ms, verified=verified,
        pixel_equal=pixel_equal, sha256=info.sha256, artifact_id=aid, params=model.params,
        peak_rss_mb=mem.peak_mb, details={"baselines": base, "normalized_from": rec["normalized_from"]})
    result["experiment_id"] = eid
    prog(1.0, "done")
    return result


def run_decompress(blob, artifact_rec=None, original=None, label="upload.ncz", progress=None):
    prog = progress or (lambda f, m=None: None)
    prog(0.02, "parsing container")
    t0 = time.perf_counter()
    err = None
    out = info = None
    with PeakMemory() as mem:
        try:
            out, info = nc.decompress(blob, progress=lambda f, m=None: prog(0.05 + 0.9 * f, m))
        except nc.NeuroCompressError as e:
            err = (type(e).__name__, str(e))
    dec_ms = (time.perf_counter() - t0) * 1000
    if err:
        db.add_experiment(kind="decompress", image_name=label, verified=False, dec_ms=dec_ms,
                          artifact_id=artifact_rec["id"] if artifact_rec else None,
                          error=f"{err[0]}: {err[1]}")
        raise ApiError(422, f"{err[0]}: {err[1]}")
    sha = nc.pixel_sha256(out)
    sha_ok = sha == info.sha256
    pixel_equal = None
    orig_name = None
    mismatches = None
    if original is None and artifact_rec and artifact_rec.get("image_id"):
        r = db.get_image(artifact_rec["image_id"])
        if r and Path(r["path"]).is_file():
            with Image.open(r["path"]) as im:
                original = np.asarray(im)
            orig_name = r["name"]
    if original is not None:
        orig_name = orig_name or "provided original"
        pixel_equal = bool(original.shape == out.shape and np.array_equal(original, out))
        mismatches = None if pixel_equal else (int((original != out).sum()) if original.shape == out.shape else -1)
    rid = uuid.uuid4().hex[:12]
    rpath = config.DATA_DIR / "reconstructions" / f"{rid}.png"
    Image.fromarray(out).save(rpath, format="PNG", compress_level=6)
    verified = sha_ok and (pixel_equal is not False)
    nm = artifact_rec["image_name"] if artifact_rec and artifact_rec.get("image_name") else label
    eid = db.add_experiment(
        kind="decompress", image_id=artifact_rec["image_id"] if artifact_rec else None, image_name=nm,
        model=info.model_name, width=info.width, height=info.height, channels=info.channels,
        raw_bytes=int(out.size), artifact_bytes=info.total_bytes, payload_bytes=info.payload_bytes,
        ratio=out.size / info.total_bytes, dec_ms=dec_ms, verified=verified, pixel_equal=pixel_equal,
        sha256=sha, artifact_id=artifact_rec["id"] if artifact_rec else None, peak_rss_mb=mem.peak_mb)
    prog(1.0, "done")
    return {
        "experiment_id": eid, "reconstruction_id": rid, "name": nm,
        "width": info.width, "height": info.height, "channels": info.channels, "model": info.model_name,
        "artifact_bytes": info.total_bytes, "raw_bytes": int(out.size), "decode_ms": round(dec_ms, 1),
        "verification": {"sha256_match": sha_ok, "stored_sha256": info.sha256, "decoded_sha256": sha,
                         "pixel_equal": pixel_equal, "compared_with": orig_name, "mismatched_samples": mismatches},
        "verified": verified, "memory": {"peak_rss_mb": mem.peak_mb, "delta_rss_mb": mem.delta_mb},
    }


def run_benchmark(images, models, verify, progress):
    if not images or not models:
        raise ApiError(400, "select at least one image and one model")
    for m in models:
        check_model(m)
    run_id = uuid.uuid4().hex[:8]
    loaded = [resolve_image(s) for s in images]
    total = len(loaded) * len(models)
    rows, done, cache = [], 0, {}
    for rec, arr in loaded:
        for m in models:
            lo = done / total
            span = 1 / total
            res = run_compress(arr, rec, m, verify=verify, compare=True, run_id=run_id, kind="benchmark",
                               baseline_cache=cache,
                               progress=lambda f, msg=None, lo=lo, span=span, nm=rec["name"], mm=m:
                               progress(lo + span * f, f"{nm} / {mm}: {msg or ''}"))
            rows.append(res)
            done += 1
    return {"run_id": run_id, "rows": rows}


# ------------------------------------------------------------------ cleanup
def cleanup_expired():
    """Delete uploaded images / artifacts / reconstructions older than the retention window."""
    cutoff = time.time() - config.RETENTION_HOURS * 3600
    removed = 0
    for table, col in (("images", "path"), ("artifacts", "path")):
        for r in db.query(f"SELECT id, {col} p FROM {table} WHERE created_at < ? AND id NOT LIKE 'sample-%'", (cutoff,)):
            try:
                Path(r["p"]).unlink(missing_ok=True)
            except OSError:
                pass
            db.execute(f"DELETE FROM {table} WHERE id=?", (r["id"],))
            removed += 1
    for sub in ("reconstructions", "tmp"):
        for p in (config.DATA_DIR / sub).glob("*"):
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except OSError:
                pass
    return removed
