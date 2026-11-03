import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, urls } from "../api";
import type { CompressResult, ImageRecord } from "../types";
import { errText, useAsync, useJob } from "../hooks";
import { Badge, Card, Dropzone, ErrorBanner, PageHeader, ProgressBar, Spinner, Stat, Toggle, VerifyBadge } from "../components/ui";
import { bytes, COLORS, ms, num, short } from "../lib/format";

export default function Compress() {
  const models = useAsync(() => api.models(), []);
  const samples = useAsync(() => api.samples(), []);
  const [image, setImage] = useState<ImageRecord | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [model, setModel] = useState("base");
  const [verify, setVerify] = useState(true);
  const [compare, setCompare] = useState(true);
  const job = useJob<CompressResult>();

  useEffect(() => {
    if (models.data && models.data.length && !models.data.some((m) => m.name === model)) setModel(models.data[0].name);
  }, [models.data, model]);

  const adopt = (rec: ImageRecord) => {
    setImage(rec);
    setPreviewUrl(urls.imagePreview(rec.id));
    job.reset();
  };
  const onFile = async (f: File) => {
    setBusy(true);
    setUploadError(null);
    try {
      adopt(await api.upload(f));
    } catch (e) {
      setUploadError(errText(e));
    } finally {
      setBusy(false);
    }
  };
  const onSample = async (name: string) => {
    if (!name) return;
    setBusy(true);
    setUploadError(null);
    try {
      adopt(await api.useSample(name));
    } catch (e) {
      setUploadError(errText(e));
    } finally {
      setBusy(false);
    }
  };
  const run = () => image && job.run(() => api.compress(image.id, model, verify, compare));
  const running = job.state.status === "running";
  const r = job.state.result;

  return (
    <>
      <PageHeader title="Image Compression" subtitle="Upload an image (or pick a bundled sample), choose a model, and run genuine neural-probability + range-coder compression on the backend." />
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-2">
          <Card title="1 · Image">
            <Dropzone accept="image/*" onFile={onFile} label="Drop an image here or click to browse (PNG, JPEG, BMP, TIFF, WebP…)" disabled={busy || running} />
            <div className="mt-3">
              <label className="label" htmlFor="sample">…or use a bundled sample</label>
              <select id="sample" className="input" value="" onChange={(e) => onSample(e.target.value)} disabled={busy || running || !samples.data}>
                <option value="">{samples.loading ? "loading…" : "choose sample"}</option>
                {samples.data?.map((s) => <option key={s.name} value={s.name}>{s.name} · {s.width}×{s.height} · {s.channels === 1 ? "gray" : "RGB"}</option>)}
              </select>
              {samples.error && <p className="mt-2 text-xs text-red-300">{samples.error}</p>}
            </div>
            {busy && <div className="mt-3 flex items-center gap-2 text-sm text-slate-400"><Spinner /> uploading…</div>}
            {uploadError && <div className="mt-3"><ErrorBanner message={uploadError} /></div>}
            {image && previewUrl && (
              <div className="mt-4">
                <img src={previewUrl} alt={image.name} className="max-h-72 w-full rounded-xl border border-navy-600 bg-navy-900 object-contain" style={{ imageRendering: image.width < 128 ? "pixelated" : "auto" }} />
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  <Badge tone="cyan">{image.name}</Badge>
                  <Badge>{image.width}×{image.height}</Badge>
                  <Badge>{image.channels === 1 ? "grayscale" : "RGB"}</Badge>
                  <Badge>file {bytes(image.file_bytes)}</Badge>
                  <Badge>raw {bytes(image.raw_bytes)}</Badge>
                  {image.normalized_from && <Badge tone="amber">{image.normalized_from}</Badge>}
                </div>
              </div>
            )}
          </Card>

          <Card title="2 · Settings">
            {models.error && <ErrorBanner message={models.error} onRetry={models.reload} />}
            <div className="grid grid-cols-2 gap-2">
              {models.data?.map((m) => (
                <button key={m.name} type="button" onClick={() => setModel(m.name)} disabled={running}
                  className={`rounded-xl border p-3 text-left transition ${model === m.name ? "border-accent-cyan bg-accent-cyan/10" : "border-navy-500 hover:border-navy-500/80 hover:bg-navy-700/40"}`}>
                  <div className="font-semibold capitalize">{m.name}</div>
                  <div className="font-mono text-xs text-slate-400">{m.params.toLocaleString()} params</div>
                  <div className="text-xs text-slate-500">{bytes(m.weights_bytes)} weights</div>
                </button>
              ))}
            </div>
            <div className="mt-4 space-y-3">
              <Toggle checked={verify} onChange={setVerify} label="Verify by decoding immediately (exact pixel + SHA-256)" />
              <Toggle checked={compare} onChange={setCompare} label="Compare against PNG and lossless WebP" />
            </div>
            <button className="btn-primary mt-5 w-full" disabled={!image || running || !models.data?.length} onClick={run}>
              {running ? <><Spinner /> Compressing…</> : "Compress image"}
            </button>
          </Card>
        </div>

        <div className="space-y-4 lg:col-span-3">
          {running && <Card title="Working"><ProgressBar value={job.state.progress} label={job.state.message} /></Card>}
          {job.state.status === "error" && <ErrorBanner message={job.state.error ?? "failed"} />}
          {!r && !running && job.state.status !== "error" && (
            <Card><div className="py-12 text-center text-sm text-slate-400">Results appear here after compression.<br />Everything shown is measured by the backend — nothing is simulated.</div></Card>
          )}
          {r && <Result r={r} />}
        </div>
      </div>
    </>
  );
}

function Result({ r }: { r: CompressResult }) {
  const png = r.baselines.png?.bytes ?? null;
  const webp = r.baselines.webp?.bytes ?? null;
  const rows = [
    { name: "Raw bitmap", bytes: r.sizes.raw_bytes, color: COLORS.raw },
    ...(png ? [{ name: "PNG", bytes: png, color: COLORS.png }] : []),
    ...(webp ? [{ name: "WebP lossless", bytes: webp, color: COLORS.webp }] : []),
    { name: "NeuroCompress", bytes: r.sizes.artifact_bytes, color: COLORS.nc },
    { name: "NC + model weights", bytes: r.sizes.effective_bytes, color: COLORS.ncEff },
  ];
  const v = r.verification;
  return (
    <>
      <Card title="Result" right={<div className="flex gap-2"><Badge tone="violet">{r.model.name}</Badge><VerifyBadge ok={v.performed ? v.pixel_equal && v.sha256_match : null} labelOk="lossless verified" /></div>}>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Compressed" value={bytes(r.sizes.artifact_bytes)} hint={`raw ${bytes(r.sizes.raw_bytes)}`} />
          <Stat label="Ratio" value={`${num(r.ratio)}×`} tone="violet" hint={`incl. model ${num(r.ratio_effective)}×`} />
          <Stat label="Reduction" value={`${num(r.reduction_pct, 1)}%`} tone="green" hint={`${num(r.bpsp, 3)} bits/sample`} />
          <Stat label="vs. uploaded file" value={`${num(r.ratio_vs_original_file)}×`} tone="amber" hint={`file was ${bytes(r.sizes.original_file_bytes)}`} />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Encode" value={ms(r.timing.encode_ms)} tone="amber" />
          <Stat label="Decode" value={ms(r.timing.decode_ms)} tone="amber" />
          <Stat label="Model" value={r.model.params.toLocaleString()} hint={`parameters · ${bytes(r.model.weights_bytes)}`} />
          <Stat label="Peak memory" value={r.memory.peak_rss_mb !== null ? `${r.memory.peak_rss_mb} MB` : "n/a"} hint={r.memory.delta_rss_mb !== null ? `+${r.memory.delta_rss_mb} MB during run` : "install psutil to measure"} />
        </div>
      </Card>

      <Card title="Size comparison">
        <div className="h-60">
          <ResponsiveContainer>
            <BarChart data={rows} layout="vertical" margin={{ left: 30, right: 20 }}>
              <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" stroke={COLORS.text} fontSize={11} tickFormatter={(x: number) => bytes(x)} />
              <YAxis type="category" dataKey="name" stroke={COLORS.text} fontSize={12} width={120} />
              <Tooltip contentStyle={{ background: "#0e1730", border: "1px solid #1e2d52", borderRadius: 12 }} formatter={(x: unknown) => [bytes(Number(x)), "size"]} />
              <Bar dataKey="bytes" radius={[0, 8, 8, 0]}>{rows.map((x) => <Cell key={x.name} fill={x.color} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Artifact = {bytes(r.sizes.payload_bytes)} entropy-coded payload + {r.sizes.header_bytes} B header/checksums. “NC + model weights” adds the {bytes(r.sizes.model_bytes)} model file that the decoder also needs. PNG/WebP are re-encoded from the same pixels (PNG level 9; WebP lossless method 6).
          {!png && " Baselines were not requested."}
        </p>
      </Card>

      <Card title="Verification & downloads">
        <div className="space-y-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">Pixel-by-pixel equality: <VerifyBadge ok={v.pixel_equal} /> SHA-256 of decoded pixels matches: <VerifyBadge ok={v.sha256_match} /></div>
          <div className="font-mono text-xs text-slate-400 break-all">sha256 {v.sha256}</div>
          {r.image.normalized_from && <div className="text-xs text-amber-300">Note: input was {r.image.normalized_from}; losslessness is verified against the normalised 8-bit pixels.</div>}
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <a className="btn-primary" href={urls.artifact(r.artifact_id)} download>⬇ Download compressed (.ncz)</a>
          <Link className="btn-ghost" to={`/decompress?artifact=${r.artifact_id}`}>Decompress & verify →</Link>
          <span className="self-center text-xs text-slate-500">experiment #{r.experiment_id} · model id {short(r.model.model_id, 8)}</span>
        </div>
      </Card>
    </>
  );
}
