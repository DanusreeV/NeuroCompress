"""Lightweight neural probability model with *integer-exact* inference.

Per-sample context (15 integer features) -> small MLP (fixed-point weights) -> parameters of a
discretised logistic distribution over the prediction residual. The distribution is quantised
(mu in quarter-pixels, log-scale on a 0.25 grid) and looked up in a precomputed integer
frequency table. All arithmetic in the forward pass is exact integer arithmetic carried out in
float64 (every intermediate stays below 2**53), so encoder and decoder agree bit-for-bit on any
platform / BLAS.
"""
import hashlib
import json
import os
import threading
from pathlib import Path

import numpy as np

NUM_FEATURES = 15
S1_BITS = 16          # fixed-point fraction bits of layer-1 weights
F_BITS = 12           # fixed-point fraction bits elsewhere
K_SCALES = 32
LS_MIN = -3.0
LS_STEP = 0.25
LS_OFFSET = int(round(-LS_MIN / LS_STEP))
TOTAL = 1 << 16
MAX_HIDDEN = 128
INPUT_SCALE = 32.0    # float-training inputs are x/32; folded into layer-1 weights at export
CONFIGS = {"tiny": (16, 16), "small": (32, 32), "base": (64, 64), "large": (128, 128)}
CONFIG_DESCRIPTIONS = {
    "tiny": "Fastest; smallest weight file.",
    "small": "Balanced speed / ratio.",
    "base": "Default; good ratio at moderate speed.",
    "large": "Best ratio; slowest, biggest weight file.",
}


def weights_dir() -> Path:
    env = os.environ.get("NC_WEIGHTS_DIR")
    return Path(env) if env else Path(__file__).resolve().parent / "weights"


# ---------------------------------------------------------------- context features
def pad_plane(plane):
    H, W = plane.shape
    P = np.full((H + 2, W + 4), 128, dtype=np.int32)
    P[2:, 2:W + 2] = plane
    return P


def med(w, n, nw):
    """LOCO-I / JPEG-LS median edge detector."""
    mx = np.maximum(w, n)
    mn = np.minimum(w, n)
    return np.where(nw >= mx, mn, np.where(nw <= mn, mx, w + n - nw))


def residual_plane(plane):
    H, W = plane.shape
    P = pad_plane(plane)
    base = med(P[2:, 1:W + 1], P[1:H + 1, 2:W + 2], P[1:H + 1, 1:W + 1])
    return plane.astype(np.int32) - base


def build_features(P, ys, xs, c, refP=None, Rprev=None, R0=None):
    """Features for pixels (ys, xs) of channel-plane ``c``. Only causal pixels of ``P`` and
    any pixels of fully-known earlier planes are read."""
    y2 = ys + 2
    x2 = xs + 2
    w = P[y2, x2 - 1]
    n = P[y2 - 1, x2]
    nw = P[y2 - 1, x2 - 1]
    ne = P[y2 - 1, x2 + 1]
    ww = P[y2, x2 - 2]
    nn = P[y2 - 2, x2]
    base = med(w, n, nw)
    X = np.zeros((len(ys), NUM_FEATURES), dtype=np.float64)
    X[:, 0] = w - base
    X[:, 1] = n - base
    X[:, 2] = nw - base
    X[:, 3] = ne - base
    X[:, 4] = ww - base
    X[:, 5] = nn - base
    if c > 0:
        cur = refP[y2, x2]
        X[:, 6] = cur - refP[y2, x2 - 1]
        X[:, 7] = cur - refP[y2 - 1, x2]
        X[:, 8] = cur - refP[y2 - 1, x2 - 1]
        X[:, 9] = cur - refP[y2 - 1, x2 + 1]
        X[:, 10] = Rprev[ys, xs]
        if c == 2:
            X[:, 11] = R0[ys, xs]
    X[:, 12 + c] = 1.0
    return X, base


# ---------------------------------------------------------------- probability tables
_tables_lock = threading.Lock()
_tables = None


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))


def build_freq_table():
    """Integer frequencies, shape (K_SCALES, 4, 256), indexed by u = residual mod 256."""
    b = np.exp(LS_MIN + LS_STEP * np.arange(K_SCALES))
    d = np.arange(-128, 128, dtype=np.float64)
    f = np.arange(4) / 4.0
    up = _sigmoid((d[None, None, :] + 0.5 - f[None, :, None]) / b[:, None, None])
    lo = _sigmoid((d[None, None, :] - 0.5 - f[None, :, None]) / b[:, None, None])
    lo[..., 0] = 0.0
    up[..., -1] = 1.0
    p = up - lo
    freq = 1 + np.floor(p * (TOTAL - 256)).astype(np.int64)
    deficit = TOTAL - freq.sum(axis=-1)
    arg = freq.argmax(axis=-1)
    kk, ff = np.meshgrid(np.arange(K_SCALES), np.arange(4), indexing="ij")
    freq[kk, ff, arg] += deficit
    freq = np.roll(freq, -128, axis=-1)  # signed-d order -> u = d mod 256 order
    assert (freq.sum(axis=-1) == TOTAL).all() and freq.min() >= 1
    return freq


def get_tables():
    """Returns (cum_rows: list[list[int]], table_sha256)."""
    global _tables
    with _tables_lock:
        if _tables is None:
            freq = build_freq_table()
            cum = np.zeros(freq.shape[:2] + (257,), dtype=np.int64)
            cum[..., 1:] = np.cumsum(freq, axis=-1)
            rows = cum.reshape(-1, 257).tolist()
            sha = hashlib.sha256(freq.astype(np.int32).tobytes()).hexdigest()
            _tables = (rows, sha)
        return _tables


# ---------------------------------------------------------------- model
class NeuralModel:
    def __init__(self, name, arrays, meta):
        self.name = name
        self.meta = meta
        self.hidden = tuple(meta["hidden"])
        self.arrays = {k: np.asarray(v) for k, v in arrays.items()}
        a = self.arrays
        self.W1 = a["W1"].astype(np.float64)
        self.B1 = a["B1"].astype(np.float64)
        self.W2 = a["W2"].astype(np.float64)
        self.B2 = a["B2"].astype(np.float64)
        self.W3 = a["W3"].astype(np.float64)
        self.B3 = a["B3"].astype(np.float64)
        self.params = int(sum(v.size for v in self.arrays.values()))
        self.weights_bytes = int(sum(v.nbytes for v in self.arrays.values()))
        h = hashlib.sha256()
        for k in ("W1", "B1", "W2", "B2", "W3", "B3"):
            h.update(self.arrays[k].tobytes())
        self.sha256 = h.hexdigest()
        self.model_id = bytes.fromhex(self.sha256[:16])

    def predict(self, X):
        """X: (n, 15) integer-valued float64 -> (mq, k) int64 arrays."""
        A1 = X @ self.W1 + self.B1
        np.clip(A1, 0.0, 2.0 ** 30, out=A1)
        h1 = np.floor(A1 / float(1 << (S1_BITS - F_BITS)))
        A2 = np.floor((h1 @ self.W2) / float(1 << F_BITS)) + self.B2
        np.clip(A2, 0.0, 2.0 ** 26, out=A2)
        O = (np.floor((A2 @ self.W3) / float(1 << F_BITS)) + self.B3).astype(np.int64)
        half = 1 << (F_BITS - 1)
        mq = np.clip((O[:, 0] * 4 + half) >> F_BITS, -508, 508)
        k = np.clip(((O[:, 1] * 4 + half) >> F_BITS) + LS_OFFSET, 0, K_SCALES - 1)
        return mq, k


def quantise_params(p):
    """float params {W1 (15,h1), b1, W2, b2, W3 (h2,2), b3} -> int arrays for NeuralModel."""
    def q(x, bits, lo, hi):
        return np.clip(np.rint(x * (1 << bits)), lo, hi)

    return {
        "W1": q(p["W1"] / INPUT_SCALE, S1_BITS, -32767, 32767).astype(np.int16),
        "B1": q(p["b1"], S1_BITS, -2 ** 31 + 1, 2 ** 31 - 1).astype(np.int32),
        "W2": q(p["W2"], F_BITS, -32767, 32767).astype(np.int16),
        "B2": q(p["b2"], F_BITS, -2 ** 31 + 1, 2 ** 31 - 1).astype(np.int32),
        "W3": q(p["W3"], F_BITS, -32767, 32767).astype(np.int16),
        "B3": q(p["b3"], F_BITS, -2 ** 31 + 1, 2 ** 31 - 1).astype(np.int32),
    }


def save_model(path, arrays, meta):
    meta = dict(meta)
    meta["table_sha256"] = get_tables()[1]
    np.savez_compressed(path, meta=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8), **arrays)


_models = {}
_models_lock = threading.Lock()


def get_model(name: str) -> NeuralModel:
    with _models_lock:
        if name in _models:
            return _models[name]
        path = weights_dir() / f"{name}.npz"
        if not path.is_file():
            raise FileNotFoundError(f"model weights not found: {path} (run backend/neurocompress/train.py)")
        with np.load(path) as z:
            meta = json.loads(bytes(z["meta"].tolist()).decode())
            arrays = {k: z[k] for k in ("W1", "B1", "W2", "B2", "W3", "B3")}
        if meta.get("table_sha256") != get_tables()[1]:
            raise RuntimeError("probability-table checksum mismatch: this platform's math library "
                               "produced a different table than the one used at training time")
        m = NeuralModel(name, arrays, meta)
        if max(m.hidden) > MAX_HIDDEN:
            raise RuntimeError("hidden size exceeds exact-arithmetic limit")
        _models[name] = m
        return m


def clear_model_cache():
    with _models_lock:
        _models.clear()


def available_models():
    names = [n for n in CONFIGS if (weights_dir() / f"{n}.npz").is_file()]
    return names


def model_info(name):
    m = get_model(name)
    info = dict(m.meta)
    info.update(name=name, description=CONFIG_DESCRIPTIONS.get(name, ""), hidden=list(m.hidden),
                params=m.params, weights_bytes=m.weights_bytes, sha256=m.sha256)
    return info
