import struct
import unittest
import zlib

import numpy as np

import neurocompress as nc
from neurocompress import baselines
from neurocompress import model as M
from neurocompress import samples as S

MODEL = "tiny" if "tiny" in M.available_models() else M.available_models()[0]


def rt(test, img, model=MODEL):
    blob = nc.compress(img, model)
    out, info = nc.decompress(blob)
    test.assertEqual(out.shape, img.shape)
    test.assertEqual(out.dtype, np.uint8)
    test.assertTrue(np.array_equal(out, img), "pixel mismatch")
    test.assertEqual(nc.pixel_sha256(out), nc.pixel_sha256(img))
    test.assertEqual(info.sha256, nc.pixel_sha256(img))
    return blob


class RoundTrip(unittest.TestCase):
    def test_rgb_and_gray_natural_like(self):
        rt(self, S.plasma(64, 48, 1))
        rt(self, S.plasma(64, 48, 2, gray=True))
        rt(self, S.shapes(70, 50, 3))

    def test_tiny_and_unusual_dimensions(self):
        rng = np.random.default_rng(0)
        for shape in [(1, 1), (1, 1, 3), (1, 9), (9, 1), (1, 9, 3), (9, 1, 3), (2, 2), (2, 2, 3), (3, 5),
                      (5, 3, 3), (1, 257), (257, 1), (31, 17, 3), (16, 16), (2, 300, 3)]:
            with self.subTest(shape=shape):
                rt(self, rng.integers(0, 256, shape, dtype=np.uint8))

    def test_patterns(self):
        for name, img in {
            "gradient": S.gradient(50, 40), "gradient_gray": S.gradient_gray(50, 40), "flat": S.flat(40, 30),
            "checker": S.checker(40, 40, 4), "stripes": S.stripes(60, 20), "noise": S.noise(30, 30, 5),
            "noise_gray": S.noise(30, 30, 6, channels=1),
        }.items():
            with self.subTest(name=name):
                rt(self, img)

    def test_extreme_values_and_wraparound(self):
        rt(self, np.zeros((20, 20, 3), np.uint8))
        rt(self, np.full((20, 20, 3), 255, np.uint8))
        alt = np.zeros((16, 16), np.uint8)
        alt[::2, ::2] = 255
        alt[1::2, 1::2] = 255
        rt(self, alt)
        rt(self, np.tile(np.array([[0, 255]], np.uint8), (12, 8)))

    def test_flat_image_compresses_well(self):
        blob = rt(self, S.flat(64, 64))
        self.assertLess(len(blob), 300)

    def test_all_available_models(self):
        img = S.shapes(40, 30, 7)
        for name in M.available_models():
            with self.subTest(model=name):
                rt(self, img, name)

    def test_deterministic_output(self):
        img = S.plasma(40, 30, 9)
        self.assertEqual(nc.compress(img, MODEL), nc.compress(img, MODEL))

    def test_natural_image_beats_raw(self):
        img = S.plasma(96, 96, 11)
        self.assertLess(len(nc.compress(img, MODEL)), img.size * 0.8)

    def test_progress_callback(self):
        seen = []
        blob = nc.compress(S.plasma(40, 30, 1), MODEL, progress=lambda f, m=None: seen.append(f))
        self.assertTrue(seen and seen[-1] <= 1.0 and seen == sorted(seen))
        seen.clear()
        nc.decompress(blob, progress=lambda f, m=None: seen.append(f))
        self.assertTrue(seen and abs(seen[-1] - 1.0) < 1e-9)


class Validation(unittest.TestCase):
    def test_rejects_bad_input(self):
        for bad in [np.zeros((4, 4), np.float32), np.zeros((4, 4, 4), np.uint8), np.zeros((0, 4), np.uint8),
                    np.zeros((4,), np.uint8), "nope"]:
            with self.assertRaises(nc.UnsupportedImageError):
                nc.compress(bad, MODEL)

    def test_size_limit(self):
        import os
        old = os.environ.get("NC_MAX_PIXELS")
        os.environ["NC_MAX_PIXELS"] = "100"
        try:
            with self.assertRaises(nc.UnsupportedImageError):
                nc.compress(np.zeros((11, 10), np.uint8), MODEL)
        finally:
            if old is None:
                del os.environ["NC_MAX_PIXELS"]
            else:
                os.environ["NC_MAX_PIXELS"] = old


def refix_crc(b):
    b = bytearray(b)
    b[-4:] = struct.pack(">I", zlib.crc32(bytes(b[:-4])) & 0xFFFFFFFF)
    return bytes(b)


class Corruption(unittest.TestCase):
    def setUp(self):
        self.img = S.noise(24, 24, 3)
        self.blob = nc.compress(self.img, MODEL)

    def test_garbage(self):
        for bad in [b"", b"x" * 10, b"NCZ1" + b"\x00" * 100, bytes(range(256)) * 4]:
            with self.assertRaises(nc.NeuroCompressError):
                nc.decompress(bad)

    def test_bit_flip_detected_by_crc(self):
        for pos in (0, 5, 40, len(self.blob) // 2, len(self.blob) - 1):
            b = bytearray(self.blob)
            b[pos] ^= 0x01
            with self.assertRaises(nc.CorruptFileError):
                nc.decompress(bytes(b))

    def test_truncated(self):
        for n in (10, len(self.blob) // 2, len(self.blob) - 1):
            with self.assertRaises(nc.CorruptFileError):
                nc.decompress(self.blob[:n])

    def test_payload_damage_with_valid_crc_is_caught_by_sha256(self):
        info = nc.inspect_artifact(self.blob)
        start = len(self.blob) - 4 - info.payload_bytes
        b = bytearray(self.blob)
        b[start + info.payload_bytes // 2] ^= 0x40
        with self.assertRaises(nc.NeuroCompressError):
            nc.decompress(refix_crc(bytes(b)))

    def test_wrong_model_id_and_oversized_header(self):
        b = bytearray(self.blob)
        b[16:24] = b"\x01" * 8
        with self.assertRaises(nc.CorruptFileError):
            nc.decompress(refix_crc(bytes(b)))
        b = bytearray(self.blob)
        b[8:12] = struct.pack(">I", 2 ** 31)
        with self.assertRaises(nc.CorruptFileError):
            nc.decompress(refix_crc(bytes(b)))

    def test_inspect(self):
        info = nc.inspect_artifact(self.blob)
        self.assertEqual((info.width, info.height, info.channels), (24, 24, 3))
        self.assertEqual(info.model_name, MODEL)
        self.assertEqual(info.total_bytes, len(self.blob))


class ModelTables(unittest.TestCase):
    def test_tables_valid(self):
        freq = M.build_freq_table()
        self.assertTrue((freq.sum(-1) == 65536).all())
        self.assertGreaterEqual(freq.min(), 1)
        rows, sha = M.get_tables()
        self.assertEqual(len(rows), M.K_SCALES * 4)
        self.assertTrue(all(r[0] == 0 and r[-1] == 65536 and len(r) == 257 for r in rows))

    def test_weights_match_table_hash_and_bounds(self):
        for name in M.available_models():
            m = M.get_model(name)
            self.assertLessEqual(max(m.hidden), M.MAX_HIDDEN)
            self.assertGreater(m.params, 0)
            self.assertEqual(m.meta["table_sha256"], M.get_tables()[1])

    def test_predict_is_integer_valued_and_deterministic(self):
        m = M.get_model(MODEL)
        rng = np.random.default_rng(0)
        X = rng.integers(-255, 256, (500, M.NUM_FEATURES)).astype(np.float64)
        X[:, 12:] = 0
        X[:, 12] = 1
        a = m.predict(X)
        b = m.predict(X.copy())
        for u, v in zip(a, b):
            self.assertTrue(np.array_equal(u, v))
        self.assertTrue(a[1].min() >= 0 and a[1].max() < M.K_SCALES)


class Baselines(unittest.TestCase):
    def test_png_webp(self):
        img = S.plasma(32, 32, 1)
        self.assertGreater(baselines.png_size(img), 0)
        w = baselines.webp_size(img)
        self.assertTrue(w is None or w > 0)
        self.assertGreater(baselines.png_size(S.plasma(32, 32, 1, gray=True)), 0)


if __name__ == "__main__":
    unittest.main()
