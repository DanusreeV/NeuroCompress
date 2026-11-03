import { Fragment, useEffect, useState } from "react";
import { api, urls } from "../api";
import { errText, useAsync } from "../hooks";
import { Badge, Card, Empty, ErrorBanner, PageHeader, Spinner, VerifyBadge } from "../components/ui";
import { bytes, ms, num, short, when } from "../lib/format";

const PAGE = 25;

export default function History() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [kind, setKind] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const [delError, setDelError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(q.trim());
      setOffset(0);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const list = useAsync(() => api.experiments(debounced, kind, PAGE, offset), [debounced, kind, offset]);
  const total = list.data?.total ?? 0;

  const del = async (id: number) => {
    if (!window.confirm(`Delete experiment #${id}?`)) return;
    try {
      setDelError(null);
      await api.deleteExperiment(id);
      list.reload();
    } catch (e) {
      setDelError(errText(e));
    }
  };

  return (
    <>
      <PageHeader title="Experiment History" subtitle="Every compression, decompression and benchmark run is persisted in SQLite on the backend.">
        <div className="flex gap-2">
          <a className="btn-ghost" href={urls.exportExperiments("csv", debounced)} download>⬇ CSV</a>
          <a className="btn-ghost" href={urls.exportExperiments("json", debounced)} download>⬇ JSON</a>
        </div>
      </PageHeader>
      <Card>
        <div className="mb-4 flex flex-wrap gap-3">
          <input className="input max-w-xs" placeholder="Search image, model, kind, hash, id…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="search" />
          <select className="input !w-auto" value={kind} onChange={(e) => { setKind(e.target.value); setOffset(0); }} aria-label="kind">
            <option value="">all kinds</option><option value="compress">compress</option><option value="decompress">decompress</option><option value="benchmark">benchmark</option>
          </select>
          {list.loading && <span className="flex items-center gap-2 text-sm text-slate-400"><Spinner /> loading</span>}
        </div>
        {list.error && <ErrorBanner message={list.error} onRetry={list.reload} />}
        {delError && <ErrorBanner message={delError} />}
        {list.data && list.data.items.length === 0 && <Empty>{debounced || kind ? "No experiments match your filters." : "No experiments yet — run a compression first."}</Empty>}
        {list.data && list.data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr>{["#", "When", "Kind", "Image", "Model", "Size", "Ratio", "b/sample", "Enc", "Dec", "Exact", ""].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
              <tbody>
                {list.data.items.map((e) => (
                  <Fragment key={e.id}>
                    <tr className="cursor-pointer border-t border-navy-600/50 hover:bg-navy-700/30" onClick={() => setOpen(open === e.id ? null : e.id)}>
                      <td className="td font-mono text-slate-500">{e.id}</td>
                      <td className="td text-slate-400">{when(e.created_at)}</td>
                      <td className="td"><Badge tone={e.kind === "decompress" ? "amber" : e.kind === "benchmark" ? "violet" : "cyan"}>{e.kind}</Badge></td>
                      <td className="td max-w-[11rem] truncate" title={e.image_name ?? ""}>{e.image_name ?? "—"}</td>
                      <td className="td">{e.model ?? "—"}</td>
                      <td className="td font-mono">{bytes(e.artifact_bytes)}</td>
                      <td className="td font-mono">{e.ratio ? `${num(e.ratio)}×` : "—"}</td>
                      <td className="td font-mono">{num(e.bpsp, 3)}</td>
                      <td className="td font-mono">{ms(e.enc_ms)}</td>
                      <td className="td font-mono">{ms(e.dec_ms)}</td>
                      <td className="td"><VerifyBadge ok={e.verified} labelOk="exact" /></td>
                      <td className="td"><button className="btn-danger !px-2 !py-1 text-xs" onClick={(ev) => { ev.stopPropagation(); del(e.id); }}>delete</button></td>
                    </tr>
                    {open === e.id && (
                      <tr className="bg-navy-900/60">
                        <td colSpan={12} className="p-4 text-xs">
                          <div className="grid gap-4 md:grid-cols-2">
                            <dl className="space-y-1 font-mono">
                              <div>dimensions: {e.width}×{e.height} · {e.channels === 1 ? "gray" : "RGB"}</div>
                              <div>raw: {bytes(e.raw_bytes)} · artifact: {bytes(e.artifact_bytes)} · payload: {bytes(e.payload_bytes)}</div>
                              <div>model weights: {bytes(e.model_bytes)} · effective: {bytes(e.effective_bytes)} ({num(e.ratio_effective)}×)</div>
                              <div>PNG: {bytes(e.png_bytes)} · WebP: {bytes(e.webp_bytes)}</div>
                              <div>params: {e.params?.toLocaleString() ?? "—"} · peak RSS: {e.peak_rss_mb ?? "n/a"} MB</div>
                              <div>sha256: {short(e.sha256, 24)} · artifact: {e.artifact_id ?? "—"}</div>
                              {e.error && <div className="text-red-300">error: {e.error}</div>}
                            </dl>
                            <div className="flex flex-wrap items-start gap-2">
                              {e.artifact_id && e.kind !== "decompress" && <a className="btn-ghost" href={urls.artifact(e.artifact_id)} download>⬇ artifact</a>}
                              {e.artifact_id && <a className="btn-ghost" href={`#/decompress?artifact=${e.artifact_id}`}>decompress →</a>}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-4 flex items-center justify-between text-sm text-slate-400">
          <span>{total ? `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}` : "0 results"}</span>
          <div className="flex gap-2">
            <button className="btn-ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>← Prev</button>
            <button className="btn-ghost" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next →</button>
          </div>
        </div>
      </Card>
    </>
  );
}
