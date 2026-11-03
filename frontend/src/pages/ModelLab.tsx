import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import type { BenchmarkResult } from "../types";
import { useAsync, useJob } from "../hooks";
import { Badge, Card, Empty, ErrorBanner, PageHeader, ProgressBar, Spinner } from "../components/ui";
import { bytes, COLORS, MODEL_COLORS, ms, num } from "../lib/format";

export default function ModelLab() {
  const models = useAsync(() => api.models(), []);
  const samples = useAsync(() => api.samples(), []);
  const [sample, setSample] = useState("");
  const job = useJob<BenchmarkResult>();
  const running = job.state.status === "running";

  if (models.loading && !models.data) return <div className="flex items-center gap-2 text-slate-400"><Spinner /> Loading models…</div>;
  if (models.error || !models.data) return <ErrorBanner message={models.error ?? "no data"} onRetry={models.reload} />;
  const ms_ = models.data;

  // Held-out bits/sample measured at training time (real codec on photos excluded from training).
  const first = ms_.find((m) => m.heldout && m.heldout.length);
  const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
  const heldChart = ms_.filter((m) => m.heldout?.length).map((m) => ({ model: m.name, bpsp: Number(mean((m.heldout ?? []).map((h) => h.nc_bpsp)).toFixed(4)) }));
  const pngRef = first?.heldout ? mean(first.heldout.map((h) => h.png_bpsp)) : null;
  const webpRef = first?.heldout ? mean(first.heldout.map((h) => h.webp_bpsp)) : null;

  const runLive = () => job.run(() => api.benchmark([{ sample }], ms_.map((m) => m.name), true));
  const live = job.state.result?.rows ?? [];

  return (
    <>
      <PageHeader title="Model Lab" subtitle="Compare the lightweight neural context models: size, training results on held-out photos, and live speed/ratio on a sample image." />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {ms_.map((m) => (
          <Card key={m.name} title={m.name}>
            <p className="text-xs text-slate-400">{m.description}</p>
            <dl className="mt-3 space-y-1.5 text-sm">
              <Row k="Architecture" v={`15 → ${m.hidden.join(" → ")} → 2`} />
              <Row k="Parameters" v={m.params.toLocaleString()} />
              <Row k="Weight file" v={bytes(m.weights_bytes)} />
              <Row k="Val. loss (float)" v={m.float_val_bits_per_sample ? `${num(m.float_val_bits_per_sample, 3)} b/sample` : "—"} />
              <Row k="Train time" v={m.train_seconds ? `${m.train_seconds}s · ${m.epochs} ep` : "—"} />
            </dl>
            <div className="mt-3 font-mono text-[10px] text-slate-600">id {m.sha256.slice(0, 16)}</div>
          </Card>
        ))}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Held-out photos · mean bits/sample (real codec)">
          {heldChart.length === 0 ? <Empty>No training metadata found in the weight files.</Empty> : (
            <>
              <div className="h-64">
                <ResponsiveContainer>
                  <BarChart data={heldChart} margin={{ left: -10, right: 10, top: 10 }}>
                    <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
                    <XAxis dataKey="model" stroke={COLORS.text} fontSize={12} />
                    <YAxis stroke={COLORS.text} fontSize={11} domain={[0, "auto"]} />
                    <Tooltip contentStyle={{ background: "#0e1730", border: "1px solid #1e2d52", borderRadius: 12 }} formatter={(v: unknown) => [`${num(Number(v), 3)} bits/sample`, "NeuroCompress"]} />
                    {pngRef !== null && <ReferenceLine y={pngRef} stroke={COLORS.png} strokeDasharray="5 4" label={{ value: "PNG", fill: COLORS.png, fontSize: 11, position: "insideTopRight" }} />}
                    {webpRef !== null && <ReferenceLine y={webpRef} stroke={COLORS.webp} strokeDasharray="5 4" label={{ value: "WebP", fill: COLORS.webp, fontSize: 11, position: "insideBottomRight" }} />}
                    <Bar dataKey="bpsp" radius={[8, 8, 0, 0]}>{heldChart.map((h) => <Cell key={h.model} fill={MODEL_COLORS[h.model] ?? COLORS.nc} />)}</Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-slate-500">Measured when the weights were trained, on 256×256 crops of {first?.heldout?.map((h) => h.image).join(", ")} (never used for training). Model weight bytes are not included.</p>
            </>
          )}
        </Card>

        <Card title="Live comparison on a sample">
          <div className="flex gap-2">
            <select className="input" value={sample} onChange={(e) => setSample(e.target.value)} disabled={running}>
              <option value="">{samples.loading ? "loading…" : "choose sample"}</option>
              {samples.data?.map((s) => <option key={s.name} value={s.name}>{s.name} · {s.width}×{s.height}</option>)}
            </select>
            <button className="btn-primary whitespace-nowrap" disabled={!sample || running} onClick={runLive}>{running ? <Spinner /> : "Run all models"}</button>
          </div>
          {running && <div className="mt-3"><ProgressBar value={job.state.progress} label={job.state.message} /></div>}
          {job.state.status === "error" && <div className="mt-3"><ErrorBanner message={job.state.error ?? "failed"} /></div>}
          {live.length > 0 && (
            <>
              <div className="mt-4 h-52">
                <ResponsiveContainer>
                  <BarChart data={live.map((r) => ({ model: r.model.name, bpsp: Number(r.bpsp.toFixed(3)), enc: Math.round(r.timing.encode_ms) }))} margin={{ left: -10, right: 10 }}>
                    <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
                    <XAxis dataKey="model" stroke={COLORS.text} fontSize={12} />
                    <YAxis yAxisId="l" stroke={COLORS.nc} fontSize={11} />
                    <YAxis yAxisId="r" orientation="right" stroke={COLORS.webp} fontSize={11} />
                    <Tooltip contentStyle={{ background: "#0e1730", border: "1px solid #1e2d52", borderRadius: 12 }} />
                    <Legend />
                    <Bar yAxisId="l" dataKey="bpsp" name="bits/sample" fill={COLORS.nc} radius={[6, 6, 0, 0]} />
                    <Bar yAxisId="r" dataKey="enc" name="encode ms" fill={COLORS.webp} radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <table className="mt-2 w-full">
                <thead><tr><th className="th">Model</th><th className="th">Size</th><th className="th">+ weights</th><th className="th">Enc</th><th className="th">Dec</th></tr></thead>
                <tbody>
                  {live.map((r) => (
                    <tr key={r.experiment_id} className="border-t border-navy-600/50">
                      <td className="td"><Badge tone="violet">{r.model.name}</Badge></td>
                      <td className="td font-mono">{bytes(r.sizes.artifact_bytes)}</td>
                      <td className="td font-mono text-slate-400">{bytes(r.sizes.effective_bytes)}</td>
                      <td className="td font-mono">{ms(r.timing.encode_ms)}</td>
                      <td className="td font-mono">{ms(r.timing.decode_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </Card>
      </div>
    </>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-slate-500">{k}</dt>
      <dd className="font-mono text-slate-200">{v}</dd>
    </div>
  );
}
