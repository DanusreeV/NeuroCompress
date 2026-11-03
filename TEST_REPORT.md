# TEST_REPORT

Produced in the build sandbox (Python 3.12, NumPy 2.4, Pillow 12.1, Node 22). **The sandbox had no network access**, so
`torch`, `fastapi`, `uvicorn`, `pytest` and all npm packages could not be installed. What that means is spelled out below;
nothing in this report is claimed without having been executed.

## Executed and passing

`cd backend && python -m unittest discover -s tests -t . -v` → **Ran 36 tests, OK (5 skipped)**

| Suite | What it covers | Result |
|---|---|---|
| `test_rangecoder` (4) | random distributions (output within 1 % of entropy bound), extreme probabilities / carry propagation, empty & single-symbol streams, truncated streams | pass |
| `test_codec` (21) | RGB + grayscale round trips; 1×1, 1×N, N×1, 2×300, 257×1 …; gradients, flat, checkerboard, stripes, uniform noise; all-0 / all-255 / alternating 0-255 (wrap-around); all four models; deterministic output; progress callback; input validation & pixel limit; **exact pixel equality + SHA-256**; garbage / bit-flip / truncation / wrong model id / oversized header / payload damage with a re-computed CRC; probability-table validity & checksum; integer-exact `predict`; PNG/WebP baselines | pass |
| `test_service` (6) | the complete application workflow at service level: upload → compress (+verify, PNG/WebP) → artifact bytes → decompress (with and without original) → reconstructed PNG equals original; gray/RGBA/palette/1-bit/JPEG uploads; invalid uploads (empty, junk, oversized pixels, oversized bytes); corrupted artifact reported (and recorded) instead of crashing; benchmark on samples; **history, stats, CSV/JSON export and search are consistent**; delete & retention cleanup | pass |
| `test_api` (5) | HTTP-level versions of the above using FastAPI `TestClient` (upload, jobs polling, downloads, CORS for another localhost port, invalid requests, benchmark, history/export) | **skipped – fastapi/httpx not installable here. Not run.** |

Additional manual runs (executed):

| Image | Model | Raw | NeuroCompress | PNG (lvl 9) | WebP lossless | Enc / Dec | Exact |
|---|---|---|---|---|---|---|---|
| photo_astronaut 256×256 RGB | base | 196,608 | 82,500 | 112,850 | 82,608 | 1.0 s / 0.6 s | yes |
| photo_coffee 171×256 RGB | large | 131,328 | 61,534 | 83,395 | 61,548 | 1.0 s / 0.6 s | yes |
| held-out rocket 400×640 RGB | base | 768,000 | 233,492 | 272,887 | 218,424 | 1.6 s / 1.5 s | yes |
| held-out camera 512×512 gray | large | 262,144 | 123,618 | 139,507 | 123,720 | 2.0 s / 1.0 s | yes |
| 1024×1024 RGB (max size) | base | 3,145,728 | 942,182 | – | – | 6.1 s / 6.0 s | yes |
| plasma_gray 192×128 | small | 24,576 | 10,193 | 11,047 | 10,274 | 0.03 s / 0.05 s | yes |
| shapes_rgb 192×128 | base | 73,728 | 23,878 | 28,902 | 24,006 | 0.1 s / 0.2 s | yes |
| white_noise 64×64 RGB | base | 12,288 | **14,535** | 12,420 | 12,410 | – | yes |
| flat_color / checkerboard / gradient_rgb | tiny / base / base | 36,864 / 36,864 / 48,000 | 423 / 933 / 5,621 | 215 / 316 / 636 | 32 / 60 / 420 | – | yes |

(Sizes exclude the model weight file: tiny 1.2 KB, small 3.4 KB, base 10.9 KB, large 38.2 KB.)

Held-out photo results (bits/sample on 256×256 crops of photos never used for training; real codec, from the weight files):

| Model | params | rocket | camera (gray) | flower | PNG (same crops) | WebP (same crops) |
|---|---|---|---|---|---|---|
| tiny | 562 | 2.259 | 2.891 | 2.380 | 2.527 / 3.527 / 3.036 | 1.961 / 2.932 / 2.425 |
| small | 1,634 | 2.220 | 2.847 | 2.360 | | |
| base | 5,314 | 2.189 | 2.844 | 2.355 | | |
| large | 18,818 | 2.126 | 2.827 | 2.336 | | |

**Honest reading:** the models always beat PNG on photographs and roughly tie lossless WebP (better on two of three crops
for gray/flower, worse on rocket). They lose clearly on synthetic graphics (flat areas, checkerboards, clean gradients – WebP/PNG
have palette/LZ tools) and **expand pure random noise by ~18 %**. Including the weight file the practical size is larger than WebP
for single images. This is a small research prototype, not a replacement for WebP.

Other executed checks: all Python files compile (`py_compile`); `bash -n scripts/start.sh`; TypeScript syntax/type check of the
whole frontend with `tsc` against stub declarations of React/Recharts/React-Router (see below).

## NOT executed (could not be run in the build environment)

* **FastAPI app / HTTP layer** — `app/main.py` was only byte-compiled; the 5 `test_api` tests are written but skipped. All logic it
  delegates to (`app/service.py`, `db.py`) *is* covered by `test_service`. Expect to run `python scripts/run_tests.py` once after
  installing requirements; any failure there would be in the thin route layer.
* **Frontend `npm install`, `npm run typecheck`, `npm run build` (Vite)** — no npm registry access. The only check done was `tsc`
  against hand-written stubs for the third-party modules: no syntax errors and no errors in the project's own types other than
  artefacts of the stubs. Real type errors involving Recharts/React-Router typings cannot be excluded. `npm run build` uses esbuild
  (no type-check), so a type nit would not block the build; `npm run typecheck` is separate.
* **Frontend ↔ backend live connectivity, start scripts (`start.ps1`, `start.sh`), Docker Compose, VS Code launch configs** — written
  carefully but never executed (`start.sh` only syntax-checked). PowerShell script was not even parsed.
* **Browser behaviour / visual design** — not rendered.
* **PyTorch** — not used. The brief asked for PyTorch; since it could not be installed or run here, training is implemented in
  NumPy (manual back-propagation) so that the shipped weights come from a script that was really executed. Inference is NumPy by design
  (integer-exact, hence encoder/decoder bit-agreement).
* Cross-platform bit-exactness (Windows/macOS) is by construction (integer-valued float64 arithmetic below 2^53, table checksum
  verified at load) but was only tested on Linux.

## Known limitations
See README → *Honest scope*. Also: a single in-process job queue (run uvicorn with one worker); jobs are lost on restart;
images up to 1,048,576 pixels; 8-bit gray/RGB only.
