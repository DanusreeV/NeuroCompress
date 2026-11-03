import { Link } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { useAsync } from "../hooks";
import { Badge, Card, Empty, ErrorBanner, PageHeader, Spinner, Stat, VerifyBadge } from "../components/ui";
import { bytes, COLORS, ms, num, when } from "../lib/format";

const tip = { contentStyle: { background: "#0e1730", border: "1px solid #1e2d52", borderRadius: 12, color: "#e2e8f0" } };

export default function Dashboard() {
  const { data: s, error, loading, reload } = useAsync(() => api.stats(), []);

  if (loading && !s) return <div className="flex items-center gap-2 text-slate-400"><Spinner /> Loading statistics from the backend…</div>;
  if (error || !s) return <ErrorBanner message={error ?? "No data"} onRetry={reload} />;

  const withBase = s.series.filter((r) => r.png_bytes && r.webp_bytes);
  const codecTotals = [
    { codec: "NeuroCompress", bytes: withBase.reduce((a, r) => a + r.artifact_bytes, 0), color: COLORS.nc },
    { codec: "PNG", bytes: withBase.reduce((a, r) => a + (r.png_bytes ?? 0), 0), color: COLORS.png },
    { codec: "WebP lossless", bytes: withBase.reduce((a, r) => a + (r.webp_bytes ?? 0), 0), color: COLORS.webp },
  ];
  const series = s.series.map((r) => ({ run: `#${r.id}`, ratio: Number(r.ratio.toFixed(3)), bpsp: Number(r.bpsp.toFixed(3)), label: `${r.image_name} · ${r.model}` }));
  const verifiedTotal = s.verified_ok + s.verified_fail;

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Live statistics computed from every experiment stored in the backend database.">
        <Link to="/compress" className="btn-primary">New compression →</Link>
      </PageHeader>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Experiments" value={s.total_experiments} hint={`${s.compressions} compress · ${s.decompressions} decompress · ${s.benchmark_rows} benchmark`} />
        <Stat label="Avg. ratio" value={s.avg_ratio ? `${num(s.avg_ratio)}×` : "—"} tone="violet" hint={`best ${s.best_ratio ? num(s.best_ratio) + "×" : "—"} · vs raw bitmap`} />
        <Stat label="Bytes saved" value={bytes(s.bytes_saved)} tone="green" hint={`${bytes(s.total_raw_bytes)} → ${bytes(s.total_artifact_bytes)}`} />
        <Stat label="Exact round trips" value={verifiedTotal ? `${s.verified_ok}/${verifiedTotal}` : "—"} tone={s.verified_fail ? "red" : "green"} hint="SHA-256 + pixel comparison" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Avg. bits / sample" value={num(s.avg_bpsp, 3)} hint="lower is better (8 = raw)" />
        <Stat label="Avg. encode" value={ms(s.avg_enc_ms)} tone="amber" />
        <Stat label="Avg. decode" value={ms(s.avg_dec_ms)} tone="amber" />
        <Stat label="Measured runs" value={s.measured_runs} hint="rows with size results" />
      </div>

      {s.total_experiments === 0 ? (
        <div className="mt-6">
          <Empty>
            No experiments yet. <Link className="text-accent-cyan underline" to="/compress">Compress an image</Link> or{" "}
            <Link className="text-accent-cyan underline" to="/benchmark">run a benchmark</Link> and the numbers will appear here.
          </Empty>
        </div>
      ) : (
        <>
          <div className="mt-6 grid gap-4 lg:grid-cols-5">
            <Card title="Compression ratio — recent runs" className="lg:col-span-3">
              <div className="h-64">
                <ResponsiveContainer>
                  <AreaChart data={series} margin={{ left: -10, right: 8, top: 8 }}>
                    <defs>
                      <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={COLORS.nc} stopOpacity={0.5} />
                        <stop offset="100%" stopColor={COLORS.nc} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
                    <XAxis dataKey="run" stroke={COLORS.text} fontSize={11} />
                    <YAxis stroke={COLORS.text} fontSize={11} />
                    <Tooltip {...tip} formatter={(v: unknown) => [`${Number(v)}×`, "ratio"]} labelFormatter={(_l: unknown, p: readonly { payload?: { label?: string } }[]) => p?.[0]?.payload?.label ?? ""} />
                    <Area type="monotone" dataKey="ratio" stroke={COLORS.nc} fill="url(#g1)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card title={`Total bytes — last ${withBase.length} runs with baselines`} className="lg:col-span-2">
              {withBase.length === 0 ? (
                <Empty>Run with “compare against PNG/WebP” enabled.</Empty>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer>
                    <BarChart data={codecTotals} margin={{ left: -10, right: 8, top: 8 }}>
                      <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
                      <XAxis dataKey="codec" stroke={COLORS.text} fontSize={11} />
                      <YAxis stroke={COLORS.text} fontSize={11} tickFormatter={(v: number) => bytes(v)} />
                      <Tooltip {...tip} formatter={(v: unknown) => [bytes(Number(v)), "total"]} />
                      <Bar dataKey="bytes" radius={[8, 8, 0, 0]}>
                        {codecTotals.map((c) => <Cell key={c.codec} fill={c.color} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-5">
            <Card title="By model" className="lg:col-span-2">
              <table className="w-full">
                <thead><tr><th className="th">Model</th><th className="th">Runs</th><th className="th">Ratio</th><th className="th">bits/sample</th><th className="th">Enc</th></tr></thead>
                <tbody>
                  {s.by_model.map((m) => (
                    <tr key={m.model} className="border-t border-navy-600/50">
                      <td className="td"><Badge tone="violet">{m.model}</Badge></td>
                      <td className="td font-mono">{m.n}</td>
                      <td className="td font-mono">{num(m.avg_ratio)}×</td>
                      <td className="td font-mono">{num(m.avg_bpsp, 3)}</td>
                      <td className="td font-mono">{ms(m.avg_enc_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card title="Recent experiments" className="lg:col-span-3" right={<Link to="/history" className="text-xs text-accent-cyan">view all →</Link>}>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead><tr><th className="th">#</th><th className="th">When</th><th className="th">Kind</th><th className="th">Image</th><th className="th">Model</th><th className="th">Ratio</th><th className="th">Exact</th></tr></thead>
                  <tbody>
                    {s.recent.map((e) => (
                      <tr key={e.id} className="border-t border-navy-600/50">
                        <td className="td font-mono text-slate-500">{e.id}</td>
                        <td className="td text-slate-400">{when(e.created_at)}</td>
                        <td className="td"><Badge tone={e.kind === "decompress" ? "amber" : e.kind === "benchmark" ? "violet" : "cyan"}>{e.kind}</Badge></td>
                        <td className="td max-w-[10rem] truncate">{e.image_name ?? "—"}</td>
                        <td className="td">{e.model ?? "—"}</td>
                        <td className="td font-mono">{e.ratio ? `${num(e.ratio)}×` : "—"}</td>
                        <td className="td"><VerifyBadge ok={e.verified} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </>
      )}
    </>
  );
}
