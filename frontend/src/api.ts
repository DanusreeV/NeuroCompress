import type {
  BenchmarkResult, CompressResult, DecompressResult, Experiment, Health, ImageRecord, Job, ModelInfo,
  SampleInfo, Stats,
} from "./types";

// Empty by default: requests go to the same origin (/api/...) and Vite proxies them to FastAPI.
const BASE: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === "object" && d !== null && "msg" in d ? String((d as { msg: unknown }).msg) : JSON.stringify(d)))
      .join("; ");
  }
  return detail ? JSON.stringify(detail) : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch {
    throw new ApiError(0, "Cannot reach the NeuroCompress backend. Is it running? (see README → Troubleshooting)");
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      msg = detailText((body as { detail?: unknown }).detail) || msg;
    } catch {
      /* non-JSON error body (e.g. proxy error) */
      if (res.status >= 500) msg = `Backend unavailable (${res.status}). Check that the backend is running.`;
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/api/health"),
  models: () => request<{ models: ModelInfo[] }>("/api/models").then((r) => r.models),
  stats: () => request<Stats>("/api/stats"),
  samples: () => request<{ samples: SampleInfo[] }>("/api/samples").then((r) => r.samples),
  useSample: (name: string) => request<ImageRecord>(`/api/samples/${encodeURIComponent(name)}/use`, { method: "POST" }),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<ImageRecord>("/api/upload", { method: "POST", body: fd });
  },
  compress: (image_id: string, model: string, verify: boolean, compare: boolean) =>
    request<{ job_id: string }>("/api/compress", json({ image_id, model, verify, compare })),
  decompress: (form: FormData) => request<{ job_id: string }>("/api/decompress", { method: "POST", body: form }),
  benchmark: (images: { image_id?: string; sample?: string }[], models: string[], verify: boolean) =>
    request<{ job_id: string }>("/api/benchmark", json({ images, models, verify })),
  job: <T,>(id: string) => request<Job<T>>(`/api/jobs/${id}`),
  experiments: (q: string, kind: string, limit: number, offset: number) => {
    const p = new URLSearchParams({ q, kind, limit: String(limit), offset: String(offset) });
    return request<{ total: number; items: Experiment[] }>(`/api/experiments?${p.toString()}`);
  },
  deleteExperiment: (id: number) => request<{ deleted: number }>(`/api/experiments/${id}`, { method: "DELETE" }),
};

export const urls = {
  imagePreview: (id: string) => `${BASE}/api/images/${id}/preview.png`,
  samplePreview: (name: string) => `${BASE}/api/samples/${encodeURIComponent(name)}/preview.png`,
  artifact: (id: string) => `${BASE}/api/artifacts/${id}/download`,
  reconstruction: (id: string, inline = false) => `${BASE}/api/reconstructions/${id}/download${inline ? "?inline=true" : ""}`,
  exportExperiments: (format: "csv" | "json", q: string) =>
    `${BASE}/api/experiments/export?format=${format}&q=${encodeURIComponent(q)}`,
};

export type { BenchmarkResult, CompressResult, DecompressResult };
