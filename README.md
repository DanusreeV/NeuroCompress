# NeuroCompress — lossless image compression with lightweight neural networks

A full-stack research dashboard + working codec. A tiny neural network predicts a probability
distribution for every pixel sample; a **real range coder** turns those probabilities into bytes.
Decoding reproduces the image **bit-for-bit** (verified by pixel comparison and SHA-256).

* **Frontend:** React + TypeScript + Vite + Tailwind + Recharts (dark research dashboard, 7 pages)
* **Backend:** Python + FastAPI + NumPy + Pillow, SQLite experiment history
* **Codec:** `backend/neurocompress/` — context model, integer-exact MLP inference, range coder, container format
* **Inspired by** *"A Learned Pixel-by-Pixel Lossless Image Compression Method with 59K Parameters and Parallel Decoding"*
  (Gumus & Kamisli). This is **not a reproduction** of that paper (see [Honest scope](#honest-scope)).

---------------------------------------------------------------------

## 1. Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.10 – 3.13 | `python --version` (Windows) / `python3 --version` (Ubuntu) |
| Node.js + npm | 18 or newer | `node --version` |
| VS Code | any recent | with the *Python* extension |

Ubuntu extras: `sudo apt install python3-venv python3-pip` (needed for virtual environments).

## 2. Quick start (recommended): one command

1. Extract `neurocompress.zip`, then in VS Code: **File → Open Folder…** → choose the `neurocompress` folder.
   Accept the "install recommended extensions" prompt.
2. Open the integrated terminal: **Terminal → New Terminal**.
3. Run the start script.

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```
**Ubuntu / Linux / macOS (bash):**
```bash
bash scripts/start.sh
```

The script (first run takes a few minutes) will: create `.env` from `.env.example`, create the virtual
environment `.venv`, install `requirements.txt`, run `npm install` in `frontend/`, choose **free ports**
(8000 / 5173 by default, the next free ones if busy), start the FastAPI backend, wait until
`/api/health` answers, then start the Vite dev server. Open the URL printed in the terminal
(normally <http://localhost:5173>). Press `Ctrl+C` to stop both.

You can also press **Ctrl+Shift+B** in VS Code (task *Start NeuroCompress*).

## 3. Manual step-by-step (two terminals)

**Terminal 1 — backend**

Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Ubuntu:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
API docs: <http://127.0.0.1:8000/docs>. Health check: <http://127.0.0.1:8000/api/health>.

**Terminal 2 — frontend** (Terminal → Split Terminal)
```bash
cd frontend
npm install
npm run dev
```
Open <http://localhost:5173>. The Vite dev server proxies every `/api/...` request to the backend, so the
browser only ever talks to one origin (no CORS problems). If your backend is **not** on port 8000, copy
`.env.example` to `.env` and set `VITE_API_PROXY_TARGET=http://127.0.0.1:<port>` (or just use the start script,
which does this for you). VS Code: select the interpreter with *Ctrl+Shift+P → Python: Select Interpreter → `.venv`*.

## 4. Single-origin production mode (no Vite)

```bash
cd frontend && npm install && npm run build && cd ..
cd backend && python -m uvicorn app.main:app --port 8000
```
FastAPI serves the built UI at <http://127.0.0.1:8000>.

## 5. Optional: Docker Compose

```bash
docker compose up --build        # UI on http://localhost:8080
```

## 6. Using the app (the acceptance workflow)

1. **Compress** → drop an image (or pick a bundled sample) → choose a model → *Compress image*.
2. Read the measured results (size, ratio, bits/sample, encode/decode time, PNG & lossless-WebP sizes, model parameters,
   memory when `psutil` is installed). Click **Download compressed (.ncz)**.
3. **Decompress** → pick the artifact (or upload the downloaded `.ncz`; optionally upload the original image) →
   *Decompress & verify*. You get the SHA-256 check, pixel-by-pixel equality and a downloadable reconstructed PNG.
4. **Benchmark Lab** compares models against PNG/WebP on many images; **Model Lab** compares model sizes and
   held-out training results; **History** searches, deletes and exports (CSV/JSON) every run; the **Dashboard**
   aggregates the same database.

Limits: uploads ≤ 20 MB and ≤ 1,048,576 pixels by default (pure NumPy decoding takes a few seconds per megapixel).
Change `NC_MAX_UPLOAD_MB` / `NC_MAX_PIXELS` in `.env`.

## 7. Project layout

```
backend/neurocompress/   codec: model.py (features, integer MLP, tables) · rangecoder.py · codec.py (container)
                         train.py (NumPy trainer) · samples.py · baselines.py (PNG/WebP) · weights/*.npz
backend/app/             FastAPI: main.py (routes) · service.py (logic) · db.py (SQLite) · jobs.py · config.py
backend/tests/           unittest suites (codec, range coder, service workflow, HTTP API)
backend/samples/         sample images  (regenerate: python scripts/generate_samples.py)
frontend/src/            React app: pages/, components/, api.ts (typed REST client), hooks.ts
scripts/                 start.ps1 · start.sh · run_tests.py · find_port.py · generate_samples.py
.vscode/                 extensions, tasks, launch configs     docker-compose.yml · TEST_REPORT.md
```

## 8. REST API (all used by the UI)

| Method & path | Purpose |
|---|---|
| `GET /api/health`, `/api/models`, `/api/stats` | status, model metadata, dashboard aggregates |
| `GET /api/samples`, `POST /api/samples/{name}/use`, `GET /api/samples/{name}/preview.png` | bundled samples |
| `POST /api/upload` (multipart `file`) → image record; `GET /api/images/{id}/preview.png` | uploads |
| `POST /api/compress` `{image_id, model, verify, compare}` → `202 {job_id}` | compression job |
| `POST /api/decompress` (multipart: `artifact_id` **or** `file`; optional `original`) → `202 {job_id}` | decompression job |
| `POST /api/benchmark` `{images:[{image_id|sample}], models:[…], verify}` → `202 {job_id}` | benchmark job |
| `GET /api/jobs/{id}` | `{status, progress, message, result, error}` (the UI polls this) |
| `GET /api/artifacts/{id}/download`, `GET /api/reconstructions/{id}/download` | downloads |
| `GET /api/experiments?q=&kind=&limit=&offset=`, `GET/DELETE /api/experiments/{id}`, `GET /api/experiments/export?format=csv\|json` | history |

## 9. How the codec works

1. Image → 8-bit planes (gray, or G,R,B). Other modes are converted and flagged in the UI.
2. For each sample: 6 causal neighbours relative to the MED (LOCO-I) prediction, plus cross-plane gradients/residuals
   for R and B → 15 integer features.
3. A small ReLU MLP (`tiny` 16×16 … `large` 128×128 hidden units) outputs a mean offset and log-scale. Inference is
   **fixed-point integer arithmetic** (exact in float64), so encoder and decoder agree on every platform.
4. The offset/scale select a discretised-logistic distribution from a 16-bit integer frequency table.
5. A range coder encodes the residual symbol. Samples are coded in wavefront order `t = x + 2y`, so the decoder
   evaluates the network for a whole anti-diagonal at once (parallel decoding of the model; the entropy decoder is serial).
6. Container `.ncz`: magic, dimensions, model name + id, SHA-256 of the pixels, payload, CRC-32.

**Practical size** = `.ncz` file. The decoder also needs the model weight file (1.2 KB – 37 KB); the UI reports both
"NC" and "NC + model weights" so small-image results are not flattering.

## 10. Re-training the models

```bash
pip install -r requirements-train.txt     # adds scikit-image / scikit-learn (sample photos)
cd backend
python -m neurocompress.train --models tiny small base large --epochs 20      # writes weights/*.npz
python -m neurocompress.train --models base --data-dir /path/to/my/images     # add your own training images
```
Training is pure NumPy (manual back-propagation, Adam, fixed seed). Results are reproducible up to floating-point
summation order. The script quantises the weights, then measures the **real codec** on photos that were held out.

## 11. Running the tests

```bash
python scripts/run_tests.py            # backend unittest + frontend typecheck/build (if npm install was done)
# or only the backend:
cd backend && python -m unittest discover -s tests -t . -v
```
See `TEST_REPORT.md` for what was actually executed when this package was built.

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| Red "Backend offline" banner / `Cannot reach the NeuroCompress backend` | Backend not running or on another port. Use the start script, or start uvicorn and set `VITE_API_PROXY_TARGET` in `.env`, then restart `npm run dev`. Test: open `http://127.0.0.1:8000/api/health`. |
| `Port 8000/5173 already in use` | The start scripts pick the next free port automatically. Manually: `--port 8001` and `VITE_API_PROXY_TARGET=http://127.0.0.1:8001`. |
| Browser console shows CORS error | You are bypassing the proxy. Browse the Vite URL (not the API) or set `VITE_API_BASE_URL` **and** make sure the page origin is `http://localhost:<port>` (any localhost port is allowed) — otherwise add it to `NC_CORS_ORIGINS`. |
| `ModuleNotFoundError: fastapi` / `numpy` | The venv is not active/selected. Activate `.venv` (see §3) and `pip install -r requirements.txt`. |
| PowerShell: "running scripts is disabled" | Use `powershell -ExecutionPolicy Bypass -File scripts\start.ps1` or `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| `python3 -m venv` fails on Ubuntu | `sudo apt install python3-venv`. |
| `npm install` errors / old Node | Install Node 18+ (<https://nodejs.org> or `nvm`). Delete `frontend/node_modules` and retry. |
| `413` on upload | Image above `NC_MAX_PIXELS` / `NC_MAX_UPLOAD_MB`; resize or raise the limits in `.env`. |
| "model weights differ…" when decompressing | The `.ncz` was made with different weights (e.g. after re-training). Decode with the original weight file. |
| "probability-table checksum mismatch" | Extremely unlikely platform math difference; report it with your OS / NumPy version. |
| Memory shows `n/a` | `pip install psutil` (included in requirements). |

## Honest scope

**Implemented and verified here:** the context model, integer-exact neural inference, range coder, container, training script,
REST backend, React frontend, PNG/WebP comparison, history/export, tests (see `TEST_REPORT.md` for exactly which ran).

**Not claimed:** reproducing the paper's architecture, 59K-parameter model, datasets or numbers. These models have 0.6k–18.8k
parameters and were trained on a small set of images in minutes on a CPU. Lossless WebP can still beat them on photographs; the
held-out numbers in `TEST_REPORT.md` / Model Lab show where. **Future work:** larger/trained-on-more-data models, mixtures of
distributions, GPU (PyTorch) training, compiled (C/Rust) entropy coding for speed, tiling for large images, 16-bit / alpha support.

Bundled sample photos (`photo_*.png`, downscaled) come from scikit-image's data set (public domain / CC0 images: astronaut, coffee, chelsea).
