"""Service-layer integration tests (no HTTP): upload -> compress -> download -> decompress -> verify."""
import csv
import io
import json
import unittest

from . import _env  # noqa: F401  (must be first)

import numpy as np
from PIL import Image

from neurocompress import model as M
from neurocompress import samples as S
from app import service
from app.service import ApiError, db

MODEL = "tiny" if "tiny" in M.available_models() else M.available_models()[0]


def png_bytes(arr, mode=None, fmt="PNG"):
    buf = io.BytesIO()
    im = Image.fromarray(arr)
    if mode:
        im = im.convert(mode)
    im.save(buf, format=fmt)
    return buf.getvalue()


class Workflow(unittest.TestCase):
    def test_full_roundtrip_rgb(self):
        arr = S.shapes(80, 60, 4)
        rec = service.ingest_upload(png_bytes(arr), "my photo.png")
        self.assertEqual((rec["width"], rec["height"], rec["channels"]), (80, 60, 3))
        rec, loaded = service.load_array(rec["id"])
        self.assertTrue(np.array_equal(loaded, arr))
        seen = []
        res = service.run_compress(loaded, rec, MODEL, progress=lambda f, m=None: seen.append(f))
        self.assertTrue(res["verification"]["pixel_equal"] and res["verification"]["sha256_match"])
        self.assertGreater(res["ratio"], 1.0)
        self.assertEqual(res["sizes"]["effective_bytes"], res["sizes"]["artifact_bytes"] + res["model"]["weights_bytes"])
        self.assertIn("png", res["baselines"])
        self.assertTrue(seen and seen[-1] == 1.0)
        # download artifact bytes then decompress them as an upload (fresh "user" path)
        art = db.get_artifact(res["artifact_id"])
        blob = open(art["path"], "rb").read()
        self.assertEqual(len(blob), res["sizes"]["artifact_bytes"])
        out = service.run_decompress(blob, artifact_rec=None, original=arr, label="x.ncz")
        self.assertTrue(out["verified"])
        self.assertTrue(out["verification"]["pixel_equal"])
        rec_png = np.asarray(Image.open(service.config.DATA_DIR / "reconstructions" / f"{out['reconstruction_id']}.png"))
        self.assertTrue(np.array_equal(rec_png, arr))
        # decompress via stored artifact (original looked up automatically)
        out2 = service.run_decompress(blob, artifact_rec=art)
        self.assertTrue(out2["verification"]["pixel_equal"])
        self.assertEqual(out2["verification"]["compared_with"], "my photo.png")

    def test_grayscale_and_modes(self):
        g = S.plasma(50, 40, 2, gray=True)
        rec = service.ingest_upload(png_bytes(g), "g.png")
        self.assertEqual(rec["channels"], 1)
        rgba = np.dstack([S.plasma(30, 20, 1), np.full((20, 30), 255, np.uint8)])
        rec = service.ingest_upload(png_bytes(rgba), "a.png")
        self.assertEqual(rec["channels"], 3)
        self.assertIn("alpha", rec["normalized_from"])
        pal = service.ingest_upload(png_bytes(S.plasma(30, 20, 1), mode="P"), "p.png")
        self.assertEqual(pal["channels"], 3)
        bw = service.ingest_upload(png_bytes(S.checker(32, 32, 4), mode="1"), "b.png")
        self.assertEqual(bw["channels"], 1)
        jpg = service.ingest_upload(png_bytes(S.plasma(40, 30, 1), fmt="JPEG"), "j.jpg")
        _, arr = service.load_array(jpg["id"])
        res = service.run_compress(arr, jpg, MODEL, verify=True)
        self.assertTrue(res["verification"]["pixel_equal"])

    def test_invalid_uploads(self):
        for data, status in [(b"", 400), (b"hello world", 400), (b"\x89PNG\r\n\x1a\n" + b"junk" * 20, 400)]:
            with self.assertRaises(ApiError) as cm:
                service.ingest_upload(data, "bad.png")
            self.assertEqual(cm.exception.status, status)
        big = np.zeros((1100, 1100), np.uint8)
        with self.assertRaises(ApiError) as cm:
            service.ingest_upload(png_bytes(big), "big.png")
        self.assertEqual(cm.exception.status, 413)
        old = service.config.MAX_UPLOAD_MB
        service.config.MAX_UPLOAD_MB = 0.0001
        try:
            with self.assertRaises(ApiError) as cm:
                service.ingest_upload(png_bytes(S.noise(40, 40, 1)), "n.png")
            self.assertEqual(cm.exception.status, 413)
        finally:
            service.config.MAX_UPLOAD_MB = old

    def test_corrupted_artifact_is_reported_not_crashing(self):
        arr = S.noise(20, 20, 2)
        rec = service.ingest_upload(png_bytes(arr), "n.png")
        _, a = service.load_array(rec["id"])
        res = service.run_compress(a, rec, MODEL)
        blob = bytearray(open(db.get_artifact(res["artifact_id"])["path"], "rb").read())
        blob[len(blob) // 2] ^= 0xFF
        before = db.stats()["total_experiments"]
        with self.assertRaises(ApiError) as cm:
            service.run_decompress(bytes(blob), label="bad.ncz")
        self.assertEqual(cm.exception.status, 422)
        self.assertEqual(db.stats()["total_experiments"], before + 1)  # failure is recorded in history

    def test_benchmark_samples_and_history_consistency(self):
        samples = service.list_samples()
        self.assertGreaterEqual(len(samples), 3)
        names = [s["name"] for s in samples[:2]]
        before = db.stats()
        res = service.run_benchmark([{"sample": n} for n in names], [MODEL], True, lambda f, m=None: None)
        self.assertEqual(len(res["rows"]), 2)
        for r in res["rows"]:
            self.assertTrue(r["verification"]["pixel_equal"])
        after = db.stats()
        self.assertEqual(after["total_experiments"], before["total_experiments"] + 2)
        total, items = db.list_experiments(limit=1000)
        self.assertEqual(total, after["total_experiments"])
        self.assertEqual(sum(1 for i in items if i["kind"] == "benchmark"), after["benchmark_rows"])
        self.assertEqual(after["total_experiments"],
                         after["compressions"] + after["decompressions"] + after["benchmark_rows"])
        # search + export
        _, found = db.list_experiments(q=names[0])
        self.assertTrue(found and all(names[0] in (f["image_name"] or "") for f in found))
        body, mime = db.export("csv")
        rows = list(csv.DictReader(io.StringIO(body)))
        self.assertEqual(len(rows), total)
        body, mime = db.export("json")
        self.assertEqual(len(json.loads(body)), total)
        with self.assertRaises(ApiError):
            service.run_benchmark([], [MODEL], True, lambda *a: None)
        with self.assertRaises(ApiError):
            service.run_benchmark([{"sample": names[0]}], ["nope"], True, lambda *a: None)

    def test_delete_and_cleanup(self):
        arr = S.noise(10, 10, 3)
        rec = service.ingest_upload(png_bytes(arr), "c.png")
        _, a = service.load_array(rec["id"])
        res = service.run_compress(a, rec, MODEL, verify=False, compare=False)
        self.assertIsNone(res["timing"]["decode_ms"])
        self.assertEqual(db.delete_experiment(res["experiment_id"]), 1)
        self.assertEqual(db.delete_experiment(res["experiment_id"]), 0)
        old = service.config.RETENTION_HOURS
        service.config.RETENTION_HOURS = -1  # everything is "expired"
        try:
            self.assertGreater(service.cleanup_expired(), 0)
        finally:
            service.config.RETENTION_HOURS = old
        with self.assertRaises(ApiError) as cm:
            service.load_array(rec["id"])
        self.assertEqual(cm.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
