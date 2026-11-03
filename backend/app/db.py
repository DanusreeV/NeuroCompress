"""SQLite persistence for images, artifacts and experiments."""
import csv
import io
import json
import sqlite3
import threading
import time

EXP_COLUMNS = [
    "kind", "created_at", "run_id", "image_id", "image_name", "model", "width", "height", "channels",
    "original_bytes", "raw_bytes", "artifact_bytes", "payload_bytes", "model_bytes", "effective_bytes",
    "ratio", "ratio_effective", "reduction_pct", "bpsp", "png_bytes", "webp_bytes", "enc_ms", "dec_ms",
    "verified", "pixel_equal", "sha256", "artifact_id", "params", "peak_rss_mb", "error", "details",
]
SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
  id TEXT PRIMARY KEY, name TEXT, width INT, height INT, channels INT, file_bytes INT, raw_bytes INT,
  sha256 TEXT, path TEXT, normalized_from TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY, path TEXT, bytes INT, image_id TEXT, image_name TEXT, model TEXT, sha256 TEXT,
  created_at REAL);
CREATE TABLE IF NOT EXISTS experiments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT, created_at REAL, run_id TEXT, image_id TEXT, image_name TEXT, model TEXT, width INT, height INT,
  channels INT, original_bytes INT, raw_bytes INT, artifact_bytes INT, payload_bytes INT, model_bytes INT,
  effective_bytes INT, ratio REAL, ratio_effective REAL, reduction_pct REAL, bpsp REAL, png_bytes INT,
  webp_bytes INT, enc_ms REAL, dec_ms REAL, verified INT, pixel_equal INT, sha256 TEXT, artifact_id TEXT,
  params INT, peak_rss_mb REAL, error TEXT, details TEXT);
CREATE INDEX IF NOT EXISTS idx_exp_created ON experiments(created_at);
"""


class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def execute(self, sql, params=()):
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # ---- images / artifacts
    def add_image(self, rec):
        cols = ("id", "name", "width", "height", "channels", "file_bytes", "raw_bytes", "sha256", "path",
                "normalized_from", "created_at")
        rec = {"created_at": time.time(), "normalized_from": None, **rec}
        self.execute(f"INSERT OR REPLACE INTO images ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                     [rec.get(c) for c in cols])

    def get_image(self, image_id):
        return self.one("SELECT * FROM images WHERE id=?", (image_id,))

    def add_artifact(self, rec):
        cols = ("id", "path", "bytes", "image_id", "image_name", "model", "sha256", "created_at")
        rec = {"created_at": time.time(), **rec}
        self.execute(f"INSERT OR REPLACE INTO artifacts ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                     [rec.get(c) for c in cols])

    def get_artifact(self, aid):
        return self.one("SELECT * FROM artifacts WHERE id=?", (aid,))

    # ---- experiments
    def add_experiment(self, **f):
        f.setdefault("created_at", time.time())
        if isinstance(f.get("details"), (dict, list)):
            f["details"] = json.dumps(f["details"])
        for k in ("verified", "pixel_equal"):
            if f.get(k) is not None:
                f[k] = int(bool(f[k]))
        cols = [c for c in EXP_COLUMNS if c in f]
        cur = self.execute(f"INSERT INTO experiments ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                           [f[c] for c in cols])
        return cur.lastrowid

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        if row.get("details"):
            try:
                row["details"] = json.loads(row["details"])
            except ValueError:
                pass
        for k in ("verified", "pixel_equal"):
            if row.get(k) is not None:
                row[k] = bool(row[k])
        return row

    def list_experiments(self, q="", kind="", limit=100, offset=0):
        where, args = [], []
        if q:
            like = f"%{q}%"
            where.append("(image_name LIKE ? OR model LIKE ? OR kind LIKE ? OR sha256 LIKE ? OR CAST(id AS TEXT)=?)")
            args += [like, like, like, like, q]
        if kind:
            where.append("kind=?")
            args.append(kind)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        total = self.one(f"SELECT COUNT(*) n FROM experiments{w}", args)["n"]
        rows = self.query(f"SELECT * FROM experiments{w} ORDER BY id DESC LIMIT ? OFFSET ?", args + [limit, offset])
        return total, [self._decode(r) for r in rows]

    def get_experiment(self, eid):
        return self._decode(self.one("SELECT * FROM experiments WHERE id=?", (eid,)))

    def delete_experiment(self, eid):
        return self.execute("DELETE FROM experiments WHERE id=?", (eid,)).rowcount

    def export(self, fmt, q=""):
        _, rows = self.list_experiments(q=q, limit=1_000_000)
        if fmt == "json":
            return json.dumps(rows, indent=2), "application/json"
        buf = io.StringIO()
        cols = ["id"] + [c for c in EXP_COLUMNS if c != "details"]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
        return buf.getvalue(), "text/csv"

    def stats(self):
        agg = self.one("""
          SELECT COUNT(*) total,
                 SUM(kind='compress') compressions, SUM(kind='decompress') decompressions,
                 SUM(kind='benchmark') benchmarks,
                 SUM(verified=1) verified_ok, SUM(verified=0) verified_fail
          FROM experiments""")
        comp = self.one("""
          SELECT COUNT(*) n, AVG(ratio) avg_ratio, MAX(ratio) best_ratio, AVG(bpsp) avg_bpsp,
                 SUM(raw_bytes) raw, SUM(artifact_bytes) art, AVG(enc_ms) avg_enc_ms, AVG(dec_ms) avg_dec_ms,
                 SUM(png_bytes) png, SUM(webp_bytes) webp
          FROM experiments WHERE kind IN ('compress','benchmark') AND artifact_bytes IS NOT NULL""")
        by_model = self.query("""
          SELECT model, COUNT(*) n, AVG(ratio) avg_ratio, AVG(bpsp) avg_bpsp, AVG(enc_ms) avg_enc_ms,
                 AVG(dec_ms) avg_dec_ms
          FROM experiments WHERE kind IN ('compress','benchmark') AND artifact_bytes IS NOT NULL
          GROUP BY model ORDER BY model""")
        series = self.query("""
          SELECT id, created_at, model, image_name, ratio, bpsp, png_bytes, webp_bytes, artifact_bytes
          FROM experiments WHERE kind IN ('compress','benchmark') AND artifact_bytes IS NOT NULL
          ORDER BY id DESC LIMIT 40""")[::-1]
        _, recent = self.list_experiments(limit=8)
        return {
            "total_experiments": agg["total"] or 0,
            "compressions": agg["compressions"] or 0,
            "decompressions": agg["decompressions"] or 0,
            "benchmark_rows": agg["benchmarks"] or 0,
            "verified_ok": agg["verified_ok"] or 0,
            "verified_fail": agg["verified_fail"] or 0,
            "measured_runs": comp["n"] or 0,
            "avg_ratio": comp["avg_ratio"], "best_ratio": comp["best_ratio"], "avg_bpsp": comp["avg_bpsp"],
            "total_raw_bytes": comp["raw"] or 0, "total_artifact_bytes": comp["art"] or 0,
            "bytes_saved": (comp["raw"] or 0) - (comp["art"] or 0),
            "total_png_bytes": comp["png"] or 0, "total_webp_bytes": comp["webp"] or 0,
            "avg_enc_ms": comp["avg_enc_ms"], "avg_dec_ms": comp["avg_dec_ms"],
            "by_model": by_model, "series": series, "recent": recent,
        }
