"""HTTP-level tests with FastAPI's TestClient. Skipped automatically when fastapi/httpx are not installed."""
import io
import time
import unittest

from . import _env  # noqa: F401

try:
    from fastapi.testclient import TestClient
    HAVE = True
except Exception:  # pragma: no cover
    HAVE = False

import numpy as np
from PIL import Image

from neurocompress import model as M
from neurocompress import samples as S

MODEL = "tiny" if "tiny" in M.available_models() else (M.available_models() or ["base"])[0]


def png(arr):
    b = io.BytesIO()
    Image.fromarray(arr).save(b, format="PNG")
    return b.getvalue()


@unittest.skipUnless(HAVE, "fastapi / httpx not installed")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.main import app
        cls.c = TestClient(app)

    def wait(self, job_id, timeout=120):
        t = time.time()
        while time.time() - t < timeout:
            j = self.c.get(f"/api/jobs/{job_id}").json()
            if j["status"] in ("done", "failed"):
                return j
            time.sleep(0.05)
        self.fail("job timed out")

    def test_health_models_cors(self):
        h = self.c.get("/api/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertIn(MODEL, h["models"])
        ms = self.c.get("/api/models").json()["models"]
        self.assertTrue(any(m["name"] == MODEL and m["params"] > 0 for m in ms))
        r = self.c.get("/api/health", headers={"Origin": "http://localhost:5199"})
        self.assertEqual(r.headers.get("access-control-allow-origin"), "http://localhost:5199")

    def test_full_workflow(self):
        arr = S.shapes(64, 48, 8)
        up = self.c.post("/api/upload", files={"file": ("pic.png", png(arr), "image/png")})
        self.assertEqual(up.status_code, 200, up.text)
        iid = up.json()["id"]
        self.assertEqual(self.c.get(f"/api/images/{iid}/preview.png").status_code, 200)
        r = self.c.post("/api/compress", json={"image_id": iid, "model": MODEL})
        self.assertEqual(r.status_code, 202)
        job = self.wait(r.json()["job_id"])
        self.assertEqual(job["status"], "done", job)
        res = job["result"]
        self.assertTrue(res["verification"]["pixel_equal"])
        dl = self.c.get(f"/api/artifacts/{res['artifact_id']}/download")
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(len(dl.content), res["sizes"]["artifact_bytes"])
        # decompress the downloaded file as a fresh upload, with the original for pixel comparison
        r = self.c.post("/api/decompress", files={"file": ("pic.ncz", dl.content),
                                                  "original": ("pic.png", png(arr), "image/png")})
        self.assertEqual(r.status_code, 202, r.text)
        job = self.wait(r.json()["job_id"])
        self.assertEqual(job["status"], "done", job)
        self.assertTrue(job["result"]["verified"])
        self.assertTrue(job["result"]["verification"]["pixel_equal"])
        rec = self.c.get(f"/api/reconstructions/{job['result']['reconstruction_id']}/download")
        self.assertTrue(np.array_equal(np.asarray(Image.open(io.BytesIO(rec.content))), arr))
        # history + stats reflect the same persisted rows
        hist = self.c.get("/api/experiments").json()
        stats = self.c.get("/api/stats").json()
        self.assertEqual(hist["total"], stats["total_experiments"])
        eid = hist["items"][0]["id"]
        self.assertEqual(self.c.get(f"/api/experiments/{eid}").status_code, 200)
        self.assertIn("image_name", self.c.get("/api/experiments/export?format=csv").text.splitlines()[0])
        self.assertEqual(self.c.delete(f"/api/experiments/{eid}").status_code, 200)
        self.assertEqual(self.c.get(f"/api/experiments/{eid}").status_code, 404)

    def test_decompress_by_artifact_id(self):
        up = self.c.post("/api/upload", files={"file": ("a.png", png(S.plasma(40, 30, 1)), "image/png")}).json()
        job = self.wait(self.c.post("/api/compress", json={"image_id": up["id"], "model": MODEL}).json()["job_id"])
        r = self.c.post("/api/decompress", data={"artifact_id": job["result"]["artifact_id"]})
        job2 = self.wait(r.json()["job_id"])
        self.assertTrue(job2["result"]["verification"]["pixel_equal"])

    def test_invalid_requests(self):
        self.assertEqual(self.c.post("/api/upload", files={"file": ("x.png", b"not an image")}).status_code, 400)
        self.assertEqual(self.c.post("/api/compress", json={"image_id": "nope", "model": MODEL}).status_code, 404)
        self.assertEqual(self.c.post("/api/compress", json={"image_id": "nope", "model": "zzz"}).status_code, 400)
        self.assertEqual(self.c.post("/api/decompress").status_code, 400)
        r = self.c.post("/api/decompress", files={"file": ("bad.ncz", b"garbage" * 20)})
        job = self.wait(r.json()["job_id"])
        self.assertEqual(job["status"], "failed")
        self.assertIn("error", job)
        self.assertEqual(self.c.get("/api/jobs/unknown").status_code, 404)
        self.assertEqual(self.c.get("/api/artifacts/unknown/download").status_code, 404)
        self.assertEqual(self.c.get("/api/experiments/export?format=xml").status_code, 400)

    def test_benchmark_and_samples(self):
        names = [s["name"] for s in self.c.get("/api/samples").json()["samples"]]
        self.assertTrue(names)
        self.assertEqual(self.c.get(f"/api/samples/{names[0]}/preview.png").status_code, 200)
        self.assertEqual(self.c.get("/api/samples/..%2Fsecret/preview.png").status_code, 404)
        r = self.c.post("/api/benchmark", json={"images": [{"sample": names[0]}], "models": [MODEL]})
        self.assertEqual(r.status_code, 202, r.text)
        job = self.wait(r.json()["job_id"])
        self.assertEqual(job["status"], "done", job)
        self.assertEqual(len(job["result"]["rows"]), 1)


if __name__ == "__main__":
    unittest.main()
