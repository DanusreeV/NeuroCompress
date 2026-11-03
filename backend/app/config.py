"""Configuration from environment variables / .env (no machine-specific paths)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_env():
    for p in (ROOT / ".env", ROOT / "backend" / ".env"):
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

DATA_DIR = Path(os.environ.get("NC_DATA_DIR") or (ROOT / "backend" / "data")).resolve()
SAMPLES_DIR = Path(os.environ.get("NC_SAMPLES_DIR") or (ROOT / "backend" / "samples")).resolve()
FRONTEND_DIST = Path(os.environ.get("NC_FRONTEND_DIST") or (ROOT / "frontend" / "dist")).resolve()
SERVE_FRONTEND = os.environ.get("NC_SERVE_FRONTEND", "1") != "0"
MAX_UPLOAD_MB = float(os.environ.get("NC_MAX_UPLOAD_MB", "20"))
MAX_PIXELS = int(os.environ.get("NC_MAX_PIXELS", "1048576"))
os.environ["NC_MAX_PIXELS"] = str(MAX_PIXELS)  # the codec reads the same limit
RETENTION_HOURS = float(os.environ.get("NC_RETENTION_HOURS", "72"))
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "NC_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
# Any localhost / 127.0.0.1 port is also allowed so a changed Vite port never breaks the app.
CORS_ORIGIN_REGEX = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

for sub in ("images", "artifacts", "reconstructions", "tmp"):
    (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
