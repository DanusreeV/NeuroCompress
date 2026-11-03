"""Run backend tests and (when npm is available) the frontend type-check + production build."""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ok = True
print("== backend tests")
ok &= subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"], cwd=ROOT / "backend") == 0
npm = shutil.which("npm")
if npm and (ROOT / "frontend" / "node_modules").is_dir():
    print("== frontend type-check")
    ok &= subprocess.call([npm, "run", "typecheck"], cwd=ROOT / "frontend") == 0
    print("== frontend production build")
    ok &= subprocess.call([npm, "run", "build"], cwd=ROOT / "frontend") == 0
else:
    print("== frontend checks skipped (run `npm install` inside frontend/ first)")
sys.exit(0 if ok else 1)
