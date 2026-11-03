"""FastAPI application: REST API for NeuroCompress (+ optional static hosting of the built frontend)."""
import time
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import neurocompress as nc
from neurocompress import model as M

from . import config, service
from .jobs import JobManager
from .service import ApiError, db

app = FastAPI(title="NeuroCompress API", version=nc.__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=config.CORS_ORIGIN_REGEX,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
jobs = JobManager(workers=2)


@app.on_event("startup")
def _startup():
    service.cleanup_expired()


@app.exception_handler(ApiError)
async def _api_error(_, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


# ------------------------------------------------------------------ request models
class CompressRequest(BaseModel):
    image_id: str
    model: str = "base"
    verify: bool = True
    compare: bool = True


class ImageRef(BaseModel):
    image_id: Optional[str] = None
    sample: Optional[str] = None


class BenchmarkRequest(BaseModel):
    images: List[ImageRef] = Field(default_factory=list)
    models: List[str] = Field(default_factory=list)
    verify: bool = True


def _public(rec: dict) -> dict:
    """Image records are returned to clients without server-side file paths."""
    return {k: v for k, v in rec.items() if k != "path"}


def _job_response(job_id: str):
    return JSONResponse(status_code=202, content={"job_id": job_id})


# ------------------------------------------------------------------ meta
@app.get("/api/health")
def health():
    return {
        "status": "ok", "version": nc.__version__, "time": time.time(),
        "models": M.available_models(),
        "limits": {"max_upload_mb": config.MAX_UPLOAD_MB, "max_pixels": config.MAX_PIXELS},
        "memory_metrics": _psutil_available(),
    }


def _psutil_available():
    try:
        import psutil  # noqa: F401
        return True
    except ImportError:
        return False


@app.get("/api/models")
def models():
    out = []
    for name in M.CONFIGS:
        if name in M.available_models():
            out.append(M.model_info(name))
    return {"models": out}


@app.get("/api/stats")
def stats():
    return db.stats()


# ------------------------------------------------------------------ images and samples
@app.get("/api/samples")
def samples():
    return {"samples": service.list_samples()}


@app.get("/api/samples/{name}/preview.png")
def sample_preview(name: str):
    return FileResponse(service.sample_path(name), media_type="image/png")


@app.post("/api/samples/{name}/use")
def use_sample(name: str):
    """Register a bundled sample as a working image so it can be compressed like an upload."""
    rec, _ = service.resolve_image({"sample": name})
    return _public(rec)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    limit = int(config.MAX_UPLOAD_MB * 2 ** 20)
    data = await file.read(limit + 1)
    rec = service.ingest_upload(data, file.filename or "image")
    return _public(rec)


@app.get("/api/images/{image_id}/preview.png")
def image_preview(image_id: str):
    rec = db.get_image(image_id)
    if not rec or not Path(rec["path"]).is_file():
        raise ApiError(404, "image not found")
    return FileResponse(rec["path"], media_type="image/png")


# ------------------------------------------------------------------ jobs
@app.post("/api/compress", status_code=202)
def compress(req: CompressRequest):
    service.check_model(req.model)
    rec, arr = service.load_array(req.image_id)
    jid = jobs.submit("compress", lambda progress: service.run_compress(
        arr, rec, req.model, verify=req.verify, compare=req.compare, progress=progress))
    return _job_response(jid)


@app.post("/api/decompress", status_code=202)
async def decompress(
    artifact_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    original: Optional[UploadFile] = File(None),
):
    label = "upload.ncz"
    art = None
    if file is not None and file.filename:
        blob = await file.read(int(config.MAX_UPLOAD_MB * 2 ** 20) + 1)
        label = service._safe_name(file.filename)
        if len(blob) > config.MAX_UPLOAD_MB * 2 ** 20:
            raise ApiError(413, "file too large")
    elif artifact_id:
        art = db.get_artifact(artifact_id)
        if not art or not Path(art["path"]).is_file():
            raise ApiError(404, f"artifact '{artifact_id}' not found")
        blob = Path(art["path"]).read_bytes()
        label = f"{art['image_name']}.{art['model']}.ncz"
    else:
        raise ApiError(400, "provide an artifact_id or upload a .ncz file")
    orig_arr = None
    if original is not None and original.filename:
        odata = await original.read(int(config.MAX_UPLOAD_MB * 2 ** 20) + 1)
        rec = service.ingest_upload(odata, original.filename)
        _, orig_arr = service.load_array(rec["id"])
    jid = jobs.submit("decompress", lambda progress: service.run_decompress(
        blob, artifact_rec=art, original=orig_arr, label=label, progress=progress))
    return _job_response(jid)


@app.post("/api/benchmark", status_code=202)
def benchmark(req: BenchmarkRequest):
    if len(req.images) * len(req.models) > 48:
        raise ApiError(400, "benchmark limited to 48 image/model combinations per run")
    for m in req.models:
        service.check_model(m)
    specs = [i.model_dump() for i in req.images]
    for s in specs:  # fail fast on missing images
        service.resolve_image(s)
    jid = jobs.submit("benchmark", lambda progress: service.run_benchmark(specs, req.models, req.verify, progress))
    return _job_response(jid)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise ApiError(404, "unknown job")
    return job


# ------------------------------------------------------------------ downloads
@app.get("/api/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str):
    art = db.get_artifact(artifact_id)
    if not art or not Path(art["path"]).is_file():
        raise ApiError(404, "artifact not found (it may have expired)")
    stem = Path(art["image_name"] or "image").stem
    return FileResponse(art["path"], media_type="application/octet-stream",
                        filename=f"{stem}.{art['model']}.ncz")


@app.get("/api/reconstructions/{rid}/download")
def download_reconstruction(rid: str, inline: bool = False):
    if not rid.isalnum():
        raise ApiError(400, "bad id")
    p = config.DATA_DIR / "reconstructions" / f"{rid}.png"
    if not p.is_file():
        raise ApiError(404, "reconstruction not found")
    if inline:
        return FileResponse(p, media_type="image/png")
    return FileResponse(p, media_type="image/png", filename=f"reconstructed_{rid}.png")


# ------------------------------------------------------------------ experiments
@app.get("/api/experiments")
def list_experiments(q: str = "", kind: str = "", limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    total, rows = db.list_experiments(q=q.strip(), kind=kind.strip(), limit=limit, offset=offset)
    return {"total": total, "items": rows}


@app.get("/api/experiments/export")
def export_experiments(format: str = "csv", q: str = ""):
    if format not in ("csv", "json"):
        raise ApiError(400, "format must be csv or json")
    body, mime = db.export(format, q.strip())
    return Response(body, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="neurocompress_experiments.{format}"'})


@app.get("/api/experiments/{eid}")
def get_experiment(eid: int):
    row = db.get_experiment(eid)
    if not row:
        raise ApiError(404, "experiment not found")
    return row


@app.delete("/api/experiments/{eid}")
def delete_experiment(eid: int):
    if not db.delete_experiment(eid):
        raise ApiError(404, "experiment not found")
    return {"deleted": eid}


# ------------------------------------------------------------------ static frontend (production / single-origin mode)
if config.SERVE_FRONTEND and (config.FRONTEND_DIST / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {"service": "NeuroCompress API", "docs": "/docs", "note": "frontend not built; use the Vite dev server"}
