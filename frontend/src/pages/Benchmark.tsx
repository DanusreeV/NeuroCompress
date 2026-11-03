import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import type { BenchmarkResult, CompressResult } from "../types";
import { errText, useAsync, useJob } from "../hooks";
import { Badge, Card, Dropzone, ErrorBanner, PageHeader, ProgressBar, Spinner, Toggle, VerifyBadge } from "../components/ui";
import { bytes, COLORS, MODEL_COLORS, ms, num } from "../lib/format";

type Metric = "bpsp" | "ratio" | "bytes";
interface Pick { key: string; label: string; ref: { image_id?: string; sample?: string } }

export default function Benchmark() {
  const samples = useAsync(() => api.samples(), []);
  const models = useAsync(() => api.models(), []);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [uploads, setUploads] = useState<Pick[]>([]);
  const [selModels, setSelModels] = useState<Record<string, boolean>>({});
  const [verify, setVerify] = useState(true);
  const [metric, setMetric] = useState<Metric>("bpsp");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const job = useJob<BenchmarkResult>();

  useEffect(() => {
    if (samples.data && Object.keys(picked).length === 0) {
      const init: Record<string, boolean> = {};
      samples.data.slice(0, 4).forEach((s) => (init[`s:${s.name}`] = true));
      setPicked(init);
    }
  }, [samples.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (models.data && Object.keys(selModels).length === 0) {
      const init: Record<string, boolean> = {};
      models.data.forEach((m) => (init[m.name] = m.name === "small" || m.name === "base"));
      if (!Object.values(init).some(Boolean) && models.data[0]) init[models.data[0].name] = true;
      setSelModels(init);
    }
  }, [models.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const all: Pick[] = [
    ...(samples.data ?? []).map((s) => ({ key: `s:${s.name}`, label: `${s.name} (${s.width}×${s.height}${s.channels === 1 ? ", gray" : ""})`, ref: { sample: s.name } })),
    ...uploads,
  ];
  const chosen = all.filter((p) => picked[p.key]);
  const chosenModels = Object.keys(selModels).filter((m) => selModels[m]);
  const running = job.state.status === "running";

  const onUpload = async (f: File) => {
    setUploadError(null);
    try {
      const rec = await api.upload(f);
      const p: Pick = { key: `u:${rec.id}`, label: `${rec.name} (upload)`, ref: { image_id: rec.id } };
      setUploads((u) => [...u, p]);
      setPicked((s) => ({ ...s, [p.key]: true }));
    } catch (e) {
      setUploadError(errText(e));
    }
  };
  const run = () => job.run(() => api.benchmark(chosen.map((c) => c.ref), chosenModels, verify));

  const rows = job.state.result?.rows ?? [];
  const chart = useMemo(() => buildChart(rows, metric), [rows, metric]);
  const modelNames = useMemo(() => Array.from(new Set(rows.map((r) => r.model.name))), [rows]);
  const unit = metric === "bpsp" ? "bits/sample" : metric === "ratio" ? "× vs raw" : "bytes";

  return (
    <>
      <PageHeader title="Benchmark Lab" subtitle="Run NeuroCompress models against PNG and lossless WebP on the same pixels. Every number comes from an actual encode (and, if enabled, decode + verify) on the backend." />
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Images">
            <div className="max-h-64 space-y-1 overflow-y-auto pr-1">
              {all.map((p) => (
                <label key={p.key} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-navy-700/50">
                  <input type="checkbox" className="accent-cyan-400" checked={!!picked[p.key]} disabled={running} onChange={(e) => setPicked((s) => ({ ...s, [p.key]: e.target.checked }))} />
                  {p.label}
                </label>
              ))}
              {samples.loading && <div className="text-sm text-slate-400">loading samples…</div>}
            </div>
            {samples.error && <ErrorBanner message={samples.error} onRetry={samples.reload} />}
            <div className="mt-3"><Dropzone accept="image/*" onFile={onUpload} label="Add your own image" disabled={running} /></div>
            {uploadError && <div className="mt-2"><ErrorBanner message={uploadError} /></div>}
          </Card>
          <Card title="Models">
            <div className="grid grid-cols-2 gap-2">
              {models.data?.map((m) => (
                <label key={m.name} className={`flex cursor-pointer items-center gap-2 rounded-xl border p-2.5 text-sm ${selModels[m.name] ? "border-accent-cyan bg-accent-cyan/10" : "border-navy-500"}`}>
                  <input type="checkbox" className="accent-cyan-400" checked={!!selModels[m.name]} disabled={running} onChange={(e) => setSelModels((s) => ({ ...s, [m.name]: e.target.checked }))} />
                  <span className="capitalize">{m.name}</span><span className="ml-auto font-mono text-xs text-slate-500">{(m.params / 1000).toFixed(1)}k</span>
                </label>
              ))}
            </div>
            {models.error && <ErrorBanner message={models.error} onRetry={models.reload} />}
            <div className="mt-4"><Toggle checked={verify} onChange={setVerify} label="Decode and verify every result" /></div>
            <button className="btn-primary mt-4 w-full" disabled={running || !chosen.length || !chosenModels.length} onClick={run}>
              {running ? <><Spinner /> Running…</> : `Run benchmark (${chosen.length * chosenModels.length} runs)`}
            </button>
            <p className="mt-2 text-xs text-slate-500">Large images with the “large” model can take a while (pure NumPy decoding).</p>
          </Card>
        </div>

        <div className="space-y-4 lg:col-span-3">
          {running && <Card title="Working"><ProgressBar value={job.state.progress} label={job.state.message} /></Card>}
          {job.state.status === "error" && <ErrorBanner message={job.state.error ?? "failed"} />}
          {!rows.length && !running && job.state.status !== "error" && <Card><div className="py-12 text-center text-sm text-slate-400">Select images and models, then run the benchmark.</div></Card>}
          {rows.length > 0 && (
            <>
              <Card title="Comparison" right={
                <select className="input !w-auto !py-1" value={metric} onChange={(e) => setMetric(e.target.value as Metric)} aria-label="metric">
                  <option value="bpsp">bits per sample (lower = better)</option>
                  <option value="ratio">compression ratio (higher = better)</option>
                  <option value="bytes">size in bytes</option>
                </select>}>
                <div className="h-72">
                  <ResponsiveContainer>
                    <BarChart data={chart} margin={{ left: -5, right: 10, top: 10 }}>
                      <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
                      <XAxis dataKey="image" stroke={COLORS.text} fontSize={11} interval={0} angle={-12} textAnchor="end" height={50} />
                      <YAxis stroke={COLORS.text} fontSize={11} />
                      <Tooltip contentStyle={{ background: "#0e1730", border: "1px solid #1e2d52", borderRadius: 12 }} formatter={(v: unknown, n: unknown) => [`${num(Number(v), metric === "bytes" ? 0 : 3)} ${unit}`, String(n)]} />
                      <Legend />
                      <Bar dataKey="PNG" fill={COLORS.png} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="WebP" fill={COLORS.webp} radius={[4, 4, 0, 0]} />
                      {modelNames.map((m) => <Bar key={m} dataKey={`NC ${m}`} fill={MODEL_COLORS[m] ?? COLORS.nc} radius={[4, 4, 0, 0]} />)}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-1 text-xs text-slate-500">Grayscale images are stored as RGB by lossless WebP, which disadvantages WebP on gray inputs. NC bars exclude the model-weight file (see table).</p>
              </Card>
              <Card title="Results">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead><tr>{["Image", "Model", "NC size", "+ model", "Ratio", "b/sample", "PNG", "WebP", "Encode", "Decode", "Exact"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.experiment_id} className="border-t border-navy-600/50">
                          <td className="td max-w-[10rem] truncate">{r.image.name}</td>
                          <td className="td"><Badge tone="violet">{r.model.name}</Badge></td>
                          <td className="td font-mono">{bytes(r.sizes.artifact_bytes)}</td>
                          <td className="td font-mono text-slate-400">{bytes(r.sizes.effective_bytes)}</td>
                          <td className="td font-mono">{num(r.ratio)}×</td>
                          <td className="td font-mono">{num(r.bpsp, 3)}</td>
                          <td className="td font-mono">{bytes(r.baselines.png?.bytes)}</td>
                          <td className="td font-mono">{bytes(r.baselines.webp?.bytes)}</td>
                          <td className="td font-mono">{ms(r.timing.encode_ms)}</td>
                          <td className="td font-mono">{ms(r.timing.decode_ms)}</td>
                          <td className="td"><VerifyBadge ok={r.verification.performed ? r.verification.pixel_equal && r.verification.sha256_match : null} labelOk="exact" /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  );
}

function buildChart(rows: CompressResult[], metric: Metric): Record<string, string | number>[] {
  const val = (b: number | undefined | null, raw: number): number | null => {
    if (!b) return null;
    return metric === "bpsp" ? (8 * b) / raw : metric === "ratio" ? raw / b : b;
  };
  const byImage = new Map<string, Record<string, string | number>>();
  for (const r of rows) {
    const entry = byImage.get(r.image.id) ?? { image: r.image.name };
    const raw = r.sizes.raw_bytes;
    const png = val(r.baselines.png?.bytes, raw);
    const webp = val(r.baselines.webp?.bytes, raw);
    if (png !== null) entry["PNG"] = Number(png.toFixed(4));
    if (webp !== null) entry["WebP"] = Number(webp.toFixed(4));
    const nc = val(r.sizes.artifact_bytes, raw);
    if (nc !== null) entry[`NC ${r.model.name}`] = Number(nc.toFixed(4));
    byImage.set(r.image.id, entry);
  }
  return Array.from(byImage.values());
}
