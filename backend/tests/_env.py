"""Imported first by service/API tests: isolates all runtime data in a temp directory."""
import atexit
import os
import shutil
import tempfile

if "NC_DATA_DIR" not in os.environ:
    _d = tempfile.mkdtemp(prefix="nc-test-")
    os.environ["NC_DATA_DIR"] = _d
    os.environ["NC_SAMPLES_DIR"] = os.path.join(_d, "samples")
    os.environ["NC_SERVE_FRONTEND"] = "0"
    atexit.register(shutil.rmtree, _d, True)
