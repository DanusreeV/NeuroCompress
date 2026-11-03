"""Deterministic synthetic test-image generators (NumPy only)."""
import numpy as np


def _resize(grid, h, w):
    gh, gw = grid.shape
    y = np.linspace(0, gh - 1, h)
    x = np.linspace(0, gw - 1, w)
    y0 = np.minimum(np.floor(y).astype(int), gh - 2) if gh > 1 else np.zeros(h, int)
    x0 = np.minimum(np.floor(x).astype(int), gw - 2) if gw > 1 else np.zeros(w, int)
    fy = (y - y0)[:, None] if gh > 1 else np.zeros((h, 1))
    fx = (x - x0)[None, :] if gw > 1 else np.zeros((1, w))
    y1 = np.minimum(y0 + 1, gh - 1)
    x1 = np.minimum(x0 + 1, gw - 1)
    top = grid[np.ix_(y0, x0)] * (1 - fx) + grid[np.ix_(y0, x1)] * fx
    bot = grid[np.ix_(y1, x0)] * (1 - fx) + grid[np.ix_(y1, x1)] * fx
    return top * (1 - fy) + bot * fy


def value_noise(h, w, rng, octaves=5, base=3, persistence=0.55):
    out = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        n = base * 2 ** o + 1
        out += amp * _resize(rng.random((n, n)), h, w)
        tot += amp
        amp *= persistence
    return out / tot


def _u8(x):
    return np.clip(np.rint(x), 0, 255).astype(np.uint8)


def flat(w=64, h=64, color=(200, 30, 90)):
    return np.broadcast_to(np.array(color, dtype=np.uint8), (h, w, 3)).copy()


def gradient(w=96, h=64, seed=0):
    xx, yy = np.meshgrid(np.linspace(0, 1, w), np.linspace(0, 1, h))
    return _u8(np.stack([255 * xx, 255 * yy, 255 * (xx + yy) / 2], -1))


def gradient_gray(w=96, h=64, seed=0):
    xx, _ = np.meshgrid(np.linspace(0, 1, w), np.linspace(0, 1, h))
    return _u8(255 * xx)


def checker(w=64, h=64, size=8, seed=0):
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((yy // size + xx // size) % 2).astype(bool)
    img = np.where(m[..., None], np.array([240, 240, 240]), np.array([20, 40, 90]))
    return img.astype(np.uint8)


def noise(w=48, h=48, seed=0, channels=3):
    rng = np.random.default_rng(seed)
    shape = (h, w, channels) if channels == 3 else (h, w)
    return rng.integers(0, 256, shape, dtype=np.uint8)


def plasma(w=160, h=120, seed=0, grain=1.5, gray=False):
    rng = np.random.default_rng(seed)
    lum = value_noise(h, w, rng)
    if gray:
        img = lum * 255 + rng.normal(0, grain, (h, w))
        return _u8(img)
    chans = []
    tint = rng.random(3)
    for ch in range(3):
        c = 0.7 * lum + 0.3 * value_noise(h, w, rng, octaves=4) * (0.5 + tint[ch])
        chans.append(c * 255 / 1.3 + rng.normal(0, grain, (h, w)))
    return _u8(np.stack(chans, -1))


def shapes(w=160, h=120, seed=0, grain=1.0):
    rng = np.random.default_rng(seed)
    img = plasma(w, h, seed + 1000, grain=0.0).astype(float) * 0.5 + 60
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(9):
        col = rng.integers(20, 240, 3)
        if rng.random() < 0.5:
            x0, y0 = rng.integers(0, w - 10), rng.integers(0, h - 10)
            x1, y1 = x0 + rng.integers(8, w // 2), y0 + rng.integers(8, h // 2)
            m = (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)
        else:
            cx, cy, r = rng.integers(0, w), rng.integers(0, h), rng.integers(6, min(w, h) // 3)
            m = (xx - cx) ** 2 + (yy - cy) ** 2 < r * r
        shade = 0.7 + 0.3 * (xx / max(w - 1, 1))
        img[m] = (col[None, :] * shade[m][:, None])
    img += rng.normal(0, grain, img.shape)
    return _u8(img)


def stripes(w=80, h=40, seed=0):
    xx = np.arange(w)[None, :].repeat(h, 0)
    return _u8(np.stack([(xx * 7) % 256, (xx * 3) % 256, np.full_like(xx, 128)], -1))


GENERATORS = {
    "gradient_rgb": lambda: gradient(160, 100),
    "gradient_gray": lambda: gradient_gray(160, 100),
    "checkerboard": lambda: checker(128, 96, 8),
    "flat_color": lambda: flat(128, 96),
    "plasma_rgb": lambda: plasma(192, 128, 3),
    "plasma_gray": lambda: plasma(192, 128, 4, gray=True),
    "shapes_rgb": lambda: shapes(192, 128, 5),
    "white_noise": lambda: noise(64, 64, 1),
}
