"""Reproducible NumPy trainer for the lightweight context models.

    python -m neurocompress.train --models tiny small base large --epochs 20

Pure NumPy (manual back-propagation + Adam). Trains a float MLP that predicts the mean offset and
log-scale of a discretised logistic distribution of the MED-prediction residual, then quantises
to the fixed-point integer model used by the codec and evaluates the *real* codec on held-out images.
Training data: synthetic images + (optionally) the sample photos bundled with scikit-image /
scikit-learn + any images in --data-dir. Held-out photos are never used for training.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import model as M
from . import samples as S

LN2 = np.log(2.0)


# ---------------------------------------------------------------- data
def _to_uint8(a):
    a = np.asarray(a)
    if a.dtype != np.uint8:
        a = np.clip(a, 0, 255).astype(np.uint8) if a.max() > 1.0 else np.rint(a * 255).astype(np.uint8)
    if a.ndim == 3 and a.shape[2] == 4:
        a = a[:, :, :3]
    return a


def _half(img):
    h, w = img.shape[0] // 2 * 2, img.shape[1] // 2 * 2
    im = img[:h, :w].astype(np.float32)
    im = (im[0::2, 0::2] + im[1::2, 0::2] + im[0::2, 1::2] + im[1::2, 1::2]) / 4
    return np.rint(im).astype(np.uint8)


def reference_images():
    """Returns (train_list, heldout_dict). Missing optional libraries are skipped."""
    train, held = [], {}
    try:
        from skimage import data as sk
        for name in ("astronaut", "coffee", "chelsea"):
            im = _to_uint8(getattr(sk, name)())
            train += [im, _half(im)]
        held["rocket"] = _to_uint8(sk.rocket())
        held["camera_gray"] = _to_uint8(sk.camera())
    except Exception as e:  # pragma: no cover
        print("scikit-image sample photos unavailable:", e)
    try:
        from sklearn.datasets import load_sample_images
        imgs = load_sample_images().images
        china, flower = _to_uint8(imgs[0]), _to_uint8(imgs[1])
        train += [china, _half(china)]
        held["flower"] = flower
    except Exception as e:  # pragma: no cover
        print("scikit-learn sample photos unavailable:", e)
    for s in range(12):
        train += [S.plasma(160, 128, 100 + s), S.shapes(160, 128, 200 + s),
                  S.plasma(160, 128, 300 + s, gray=True)]
    train += [S.gradient(128, 96), S.gradient_gray(128, 96), S.stripes(96, 48), S.flat(96, 64),
              S.flat(64, 64, (0, 0, 0)), S.flat(64, 64, (255, 255, 255))]
    for s in range(10):  # noise-free graphics (screenshots, diagrams, renders)
        train += [S.shapes(160, 128, 400 + s, grain=0.0), S.plasma(128, 96, 500 + s, grain=0.0),
                  S.checker(96, 96, 4 + s)]
    train += [S.plasma(128, 96, 600 + s, grain=0.0, gray=True) for s in range(4)]
    return train, held


def load_dir(path):
    from PIL import Image
    out = []
    for p in sorted(Path(path).rglob("*")):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
            im = Image.open(p)
            im = im.convert("L" if im.mode in ("L", "1") else "RGB")
            out.append(np.asarray(im, dtype=np.uint8))
    return out


def image_samples(img, per_plane, rng):
    from .codec import _planes
    planes = _planes(img)
    Xs, ds = [], []
    R = []
    P0 = None
    for c, plane in enumerate(planes):
        H, W = plane.shape
        P = M.pad_plane(plane)
        if c == 0:
            P0 = P
        n = H * W
        idx = rng.choice(n, size=min(per_plane, n), replace=False)
        ys, xs = np.divmod(idx, W)
        X, base = M.build_features(P, ys, xs, c, P0, R[c - 1] if c else None, R[0] if c else None)
        d = ((plane[ys, xs].astype(np.int64) - base + 128) & 255) - 128
        Xs.append(X.astype(np.float32))
        ds.append(d.astype(np.float32))
        R.append(M.residual_plane(plane))
    return np.concatenate(Xs), np.concatenate(ds)


def build_dataset(images, per_plane, seed):
    rng = np.random.default_rng(seed)
    X, d = zip(*[image_samples(im, per_plane, rng) for im in images])
    X, d = np.concatenate(X), np.concatenate(d)
    perm = rng.permutation(len(d))
    return X[perm], d[perm]


# ---------------------------------------------------------------- float model
def _sig(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))


def nll_bits(mu, ls, d, need_grad=True):
    b = np.exp(ls)
    a = (d + 0.5 - mu) / b
    c = (d - 0.5 - mu) / b
    sa, sc = _sig(a), _sig(c)
    pos = c > 0
    P = np.where(pos, _sig(-c) - _sig(-a), sa - sc)
    P = np.maximum(P, 1e-30)
    loss = -np.log(P) / LN2
    if not need_grad:
        return loss
    dsa, dsc = sa * (1 - sa), sc * (1 - sc)
    dP_dmu = -(dsa - dsc) / b
    dP_dls = -a * dsa + c * dsc
    g = -1.0 / (P * LN2)
    return loss, np.clip(g * dP_dmu, -20, 20), np.clip(g * dP_dls, -20, 20)


def init_params(h1, h2, rng):
    p = {
        "W1": rng.normal(0, np.sqrt(2 / M.NUM_FEATURES), (M.NUM_FEATURES, h1)),
        "b1": np.zeros(h1),
        "W2": rng.normal(0, np.sqrt(2 / h1), (h1, h2)),
        "b2": np.zeros(h2),
        "W3": rng.normal(0, 0.01, (h2, 2)),
        "b3": np.array([0.0, 1.5]),
    }
    return p


LS_HI = M.LS_MIN + M.LS_STEP * (M.K_SCALES - 1)


def forward(p, X):
    Xs = X / M.INPUT_SCALE
    z1 = Xs @ p["W1"] + p["b1"]
    h1 = np.maximum(z1, 0)
    z2 = h1 @ p["W2"] + p["b2"]
    h2 = np.maximum(z2, 0)
    o = h2 @ p["W3"] + p["b3"]
    return Xs, z1, h1, z2, h2, o


def batch_loss_grad(p, X, d):
    Xs, z1, h1, z2, h2, o = forward(p, X)
    mu = np.clip(o[:, 0], -127, 127)
    ls = np.clip(o[:, 1], M.LS_MIN, LS_HI)
    loss, gmu, gls = nll_bits(mu, ls, d)
    gmu = gmu * (np.abs(o[:, 0]) < 127)
    gls = gls * ((o[:, 1] > M.LS_MIN) & (o[:, 1] < LS_HI))
    n = len(d)
    go = np.stack([gmu, gls], 1) / n
    g = {}
    g["W3"] = h2.T @ go
    g["b3"] = go.sum(0)
    gh2 = (go @ p["W3"].T) * (z2 > 0)
    g["W2"] = h1.T @ gh2
    g["b2"] = gh2.sum(0)
    gh1 = (gh2 @ p["W2"].T) * (z1 > 0)
    g["W1"] = Xs.T @ gh1
    g["b1"] = gh1.sum(0)
    return loss.mean(), g


def eval_bits(p, X, d, bs=65536):
    tot = 0.0
    for a in range(0, len(d), bs):
        o = forward(p, X[a:a + bs])[-1]
        mu = np.clip(o[:, 0], -127, 127)
        ls = np.clip(o[:, 1], M.LS_MIN, LS_HI)
        tot += nll_bits(mu, ls, d[a:a + bs], need_grad=False).sum()
    return tot / len(d)


def train_model(hidden, X, d, Xv, dv, epochs, lr, batch, seed, log=print):
    rng = np.random.default_rng(seed)
    p = init_params(*hidden, rng)
    m = {k: np.zeros_like(v) for k, v in p.items()}
    v = {k: np.zeros_like(x) for k, x in p.items()}
    steps_per = max(1, len(d) // batch)
    total = epochs * steps_per
    t = 0
    best, best_p = 1e9, None
    for ep in range(epochs):
        perm = rng.permutation(len(d))
        for s in range(steps_per):
            idx = perm[s * batch:(s + 1) * batch]
            _, g = batch_loss_grad(p, X[idx].astype(np.float64), d[idx].astype(np.float64))
            t += 1
            cur_lr = lr * (0.05 + 0.95 * 0.5 * (1 + np.cos(np.pi * t / total)))
            for k in p:
                m[k] = 0.9 * m[k] + 0.1 * g[k]
                v[k] = 0.999 * v[k] + 0.001 * g[k] ** 2
                p[k] -= cur_lr * (m[k] / (1 - 0.9 ** t)) / (np.sqrt(v[k] / (1 - 0.999 ** t)) + 1e-8)
        vb = eval_bits(p, Xv.astype(np.float64), dv.astype(np.float64))
        if vb < best:
            best, best_p = vb, {k: x.copy() for k, x in p.items()}
        log(f"  epoch {ep + 1:2d}/{epochs}  val {vb:.4f} bits/sample")
    return best_p, best


# ---------------------------------------------------------------- evaluation
def evaluate_heldout(name, held):
    from . import codec
    from .baselines import png_size, webp_size
    res = []
    for iname, img in held.items():
        sub = img[:256, :256] if img.shape[0] * img.shape[1] > 65536 else img
        t = time.time()
        blob = codec.compress(sub, name)
        te = time.time() - t
        n = sub.size
        res.append({"image": iname, "shape": list(sub.shape), "nc_bytes": len(blob),
                    "nc_bpsp": 8 * len(blob) / n, "png_bpsp": 8 * png_size(sub) / n,
                    "webp_bpsp": 8 * (webp_size(sub) or 0) / n, "enc_seconds": round(te, 2)})
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=list(M.CONFIGS))
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--batch", type=int, default=2048)
    ap.add_argument("--per-plane", type=int, default=40000, help="pixels sampled per image plane")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--data-dir", help="extra training images (png/jpg/...)")
    ap.add_argument("--out", default=str(M.weights_dir()))
    a = ap.parse_args(argv)

    train_imgs, held = reference_images()
    if a.data_dir:
        train_imgs += load_dir(a.data_dir)
    print(f"{len(train_imgs)} training images, {len(held)} held-out photos: {list(held)}")
    X, d = build_dataset(train_imgs, a.per_plane, a.seed)
    nv = max(20000, len(d) // 20)
    Xv, dv, X, d = X[:nv], d[:nv], X[nv:], d[nv:]
    print(f"{len(d)} training samples, {nv} validation samples")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in a.models:
        hidden = M.CONFIGS[name]
        print(f"== training '{name}' hidden={hidden}")
        t0 = time.time()
        p, best = train_model(hidden, X, d, Xv, dv, a.epochs, a.lr, a.batch, a.seed)
        arrays = M.quantise_params(p)
        meta = {"name": name, "hidden": list(hidden), "float_val_bits_per_sample": float(best),
                "epochs": a.epochs, "seed": a.seed, "train_samples": int(len(d)),
                "train_seconds": round(time.time() - t0, 1),
                "trained_with": "NumPy manual backprop + Adam; synthetic + bundled sample photos",
                "heldout_images": list(held)}
        M.save_model(out / f"{name}.npz", arrays, meta)
        M.clear_model_cache()
        import os
        os.environ["NC_WEIGHTS_DIR"] = str(out)
        meta["heldout"] = evaluate_heldout(name, held)
        M.save_model(out / f"{name}.npz", arrays, meta)
        M.clear_model_cache()
        for r in meta["heldout"]:
            print(f"   {r['image']:12s} NC {r['nc_bpsp']:.3f}  PNG {r['png_bpsp']:.3f}  WebP {r['webp_bpsp']:.3f} bits/sample")
    print("done ->", out)


if __name__ == "__main__":
    main()
