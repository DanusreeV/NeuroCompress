"""Tiny in-process job runner with progress reporting."""
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor


class JobManager:
    def __init__(self, workers=2):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="nc-job")
        self.jobs = {}
        self.lock = threading.Lock()

    def submit(self, kind, fn):
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "kind": kind, "status": "queued", "progress": 0.0, "message": "queued",
               "result": None, "error": None, "created_at": time.time(), "finished_at": None}
        with self.lock:
            self._gc()
            self.jobs[jid] = job

        def progress(frac, msg=None):
            job["progress"] = max(0.0, min(1.0, float(frac)))
            if msg:
                job["message"] = msg

        def run():
            job["status"] = "running"
            job["message"] = "running"
            try:
                job["result"] = fn(progress)
                job["progress"] = 1.0
                job["status"] = "done"
                job["message"] = "done"
            except Exception as e:  # noqa: BLE001 - reported to the client
                job["status"] = "failed"
                job["error"] = {"type": type(e).__name__, "message": str(e)}
                job["message"] = str(e)
                if not _expected(e):
                    traceback.print_exc()
            finally:
                job["finished_at"] = time.time()

        self.pool.submit(run)
        return jid

    def get(self, jid):
        return self.jobs.get(jid)

    def _gc(self):
        now = time.time()
        for k in [k for k, j in self.jobs.items() if j["finished_at"] and now - j["finished_at"] > 3600]:
            del self.jobs[k]


def _expected(e):
    from neurocompress import NeuroCompressError
    return isinstance(e, (NeuroCompressError, ValueError, LookupError))
