import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, urls } from "../api";
import type { DecompressResult } from "../types";
import { useAsync, useJob } from "../hooks";
import { Badge, Card, Dropzone, ErrorBanner, PageHeader, ProgressBar, Spinner, Stat, VerifyBadge } from "../components/ui";
import { bytes, ms, num, when } from "../lib/format";

export default function Decompress() {
  const [params] = useSearchParams();
  const [artifactId, setArtifactId] = useState(params.get("artifact") ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [original, setOriginal] = useState<File | null>(null);
  const job = useJob<DecompressResult>();
  const recent = useAsync(() => api.experiments("", "", 200, 0), []);

  const artifacts = (recent.data?.items ?? []).filter((e) => e.artifact_id && e.kind !== "decompress");
  useEffect(() => {
    const a = params.get("artifact");
    if (a) setArtifactId(a);
  }, [params]);

  const run = () => {
    const fd = new FormData();
    if (file) fd.append("file", file);
    else fd.append("artifact_id", artifactId);
    if (original) fd.append("original", original);
    job.run(() => api.decompress(fd)).then(() => recent.reload());
  };
  const running = job.state.status === "running";
  const r = job.state.result;
  const canRun = (file !== null || artifactId !== "") && !running;

  return (
    <>
      <PageHeader title="Decompression" subtitle="Decode a .ncz artifact on the backend and verify exact reconstruction using the SHA-256 stored in the file and (optionally) a pixel comparison against the original." />
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-2">
          <Card title="1 · Compressed artifact">
            <label className="label" htmlFor="art">From a previous run</label>
            <select id="art" className="input" value={file ? "" : artifactId} disabled={!!file || running} onChange={(e) => setArtifactId(e.target.value)}>
              <option value="">{recent.loading ? "loading…" : artifacts.length ? "choose an artifact" : "no artifacts yet"}</option>
              {artifactId && !artifacts.some((a) => a.artifact_id === artifactId) && <option value={artifactId}>{artifactId} (from link)</option>}
              {artifacts.map((e) => <option key={e.id} value={e.artifact_id ?? ""}>#{e.id} · {e.image_name} · {e.model} · {bytes(e.artifact_bytes)} · {when(e.created_at)}</option>)}
            </select>
            {recent.error && <p className="mt-2 text-xs text-red-300">{recent.error}</p>}
            <div className="my-3 text-center text-xs text-slate-500">— or —</div>
            <Dropzone accept=".ncz" onFile={setFile} label={file ? `Selected: ${file.name} (${bytes(file.size)})` : "Drop a downloaded .ncz file"} disabled={running} />
            {file && <button className="btn-ghost mt-2 !py-1 text-xs" onClick={() => setFile(null)}>clear file</button>}
          </Card>
          <Card title="2 · Original image (optional)">
            <Dropzone accept="image/*" onFile={setOriginal} label={original ? `Selected: ${original.name}` : "Provide the original for a pixel-by-pixel comparison"} disabled={running} />
            <p className="mt-2 text-xs text-slate-500">Artifacts created in this app are compared against their stored original automatically.</p>
            {original && <button className="btn-ghost mt-2 !py-1 text-xs" onClick={() => setOriginal(null)}>clear original</button>}
          </Card>
          <button className="btn-primary w-full" disabled={!canRun} onClick={run}>{running ? <><Spinner /> Decoding…</> : "Decompress & verify"}</button>
        </div>

        <div className="space-y-4 lg:col-span-3">
          {running && <Card title="Working"><ProgressBar value={job.state.progress} label={job.state.message} /></Card>}
          {job.state.status === "error" && (
            <Card title="Decompression failed">
              <ErrorBanner message={job.state.error ?? "failed"} />
              <p className="mt-3 text-xs text-slate-500">Corrupted, truncated or foreign files are detected by the CRC-32 / structure checks and the embedded SHA-256 — they never produce a silently wrong image.</p>
            </Card>
          )}
          {!r && !running && job.state.status !== "error" && <Card><div className="py-12 text-center text-sm text-slate-400">Pick an artifact and press “Decompress & verify”.</div></Card>}
          {r && (
            <>
              <Card title="Verification" right={<VerifyBadge ok={r.verified} labelOk="exact reconstruction" labelBad="verification failed" />}>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <Stat label="Decode time" value={ms(r.decode_ms)} tone="amber" />
                  <Stat label="Dimensions" value={`${r.width}×${r.height}`} hint={r.channels === 1 ? "grayscale" : "RGB"} />
                  <Stat label="Artifact" value={bytes(r.artifact_bytes)} hint={`→ ${bytes(r.raw_bytes)} raw (${num(r.raw_bytes / r.artifact_bytes)}×)`} />
                  <Stat label="Model" value={r.model} tone="violet" />
                </div>
                <div className="mt-4 space-y-2 text-sm">
                  <div className="flex flex-wrap items-center gap-2">SHA-256 of decoded pixels equals stored hash: <VerifyBadge ok={r.verification.sha256_match} /></div>
                  <div className="flex flex-wrap items-center gap-2">
                    Pixel-by-pixel equality with original: <VerifyBadge ok={r.verification.pixel_equal} labelNone="no original available" />
                    {r.verification.compared_with && <Badge>{r.verification.compared_with}</Badge>}
                    {r.verification.mismatched_samples ? <Badge tone="red">{r.verification.mismatched_samples} samples differ</Badge> : null}
                  </div>
                  <div className="break-all font-mono text-xs text-slate-500">decoded {r.verification.decoded_sha256}</div>
                  <div className="break-all font-mono text-xs text-slate-500">stored&nbsp;&nbsp; {r.verification.stored_sha256}</div>
                </div>
              </Card>
              <Card title="Reconstructed image" right={<a className="btn-primary !py-1.5" href={urls.reconstruction(r.reconstruction_id)} download>⬇ Download PNG</a>}>
                <img src={urls.reconstruction(r.reconstruction_id, true)} alt="reconstructed" className="max-h-96 w-full rounded-xl border border-navy-600 bg-navy-900 object-contain" />
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  );
}
