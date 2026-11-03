export interface Health {
  status: string;
  version: string;
  models: string[];
  limits: { max_upload_mb: number; max_pixels: number };
  memory_metrics: boolean;
}

export interface ImageRecord {
  id: string;
  name: string;
  width: number;
  height: number;
  channels: number;
  file_bytes: number;
  raw_bytes: number;
  sha256: string;
  normalized_from: string | null;
}

export interface SampleInfo {
  name: string;
  width: number;
  height: number;
  channels: number;
  file_bytes: number;
}

export interface HeldoutResult {
  image: string;
  shape: number[];
  nc_bytes: number;
  nc_bpsp: number;
  png_bpsp: number;
  webp_bpsp: number;
  enc_seconds: number;
}

export interface ModelInfo {
  name: string;
  description: string;
  hidden: number[];
  params: number;
  weights_bytes: number;
  sha256: string;
  float_val_bits_per_sample?: number;
  epochs?: number;
  train_samples?: number;
  train_seconds?: number;
  trained_with?: string;
  heldout?: HeldoutResult[];
}

export interface BaselineEntry {
  bytes: number;
  encode_ms: number;
}

export interface CompressResult {
  experiment_id: number;
  artifact_id: string;
  image: { id: string; name: string; width: number; height: number; channels: number; normalized_from: string | null };
  model: { name: string; params: number; weights_bytes: number; hidden: number[]; model_id: string };
  sizes: {
    original_file_bytes: number;
    raw_bytes: number;
    artifact_bytes: number;
    payload_bytes: number;
    header_bytes: number;
    model_bytes: number;
    effective_bytes: number;
  };
  ratio: number;
  ratio_effective: number;
  reduction_pct: number;
  ratio_vs_original_file: number;
  bpsp: number;
  timing: { encode_ms: number; decode_ms: number | null };
  verification: { performed: boolean; pixel_equal: boolean | null; sha256_match: boolean | null; sha256: string };
  memory: { peak_rss_mb: number | null; delta_rss_mb: number | null; model_weights_bytes: number };
  baselines: { png?: BaselineEntry | null; webp?: BaselineEntry | null };
}

export interface DecompressResult {
  experiment_id: number;
  reconstruction_id: string;
  name: string;
  width: number;
  height: number;
  channels: number;
  model: string;
  artifact_bytes: number;
  raw_bytes: number;
  decode_ms: number;
  verification: {
    sha256_match: boolean;
    stored_sha256: string;
    decoded_sha256: string;
    pixel_equal: boolean | null;
    compared_with: string | null;
    mismatched_samples: number | null;
  };
  verified: boolean;
  memory: { peak_rss_mb: number | null; delta_rss_mb: number | null };
}

export interface BenchmarkResult {
  run_id: string;
  rows: CompressResult[];
}

export interface JobError {
  type: string;
  message: string;
}

export interface Job<T> {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  progress: number;
  message: string;
  result: T | null;
  error: JobError | null;
}

export interface Experiment {
  id: number;
  kind: "compress" | "decompress" | "benchmark";
  created_at: number;
  run_id: string | null;
  image_id: string | null;
  image_name: string | null;
  model: string | null;
  width: number | null;
  height: number | null;
  channels: number | null;
  original_bytes: number | null;
  raw_bytes: number | null;
  artifact_bytes: number | null;
  payload_bytes: number | null;
  model_bytes: number | null;
  effective_bytes: number | null;
  ratio: number | null;
  ratio_effective: number | null;
  reduction_pct: number | null;
  bpsp: number | null;
  png_bytes: number | null;
  webp_bytes: number | null;
  enc_ms: number | null;
  dec_ms: number | null;
  verified: boolean | null;
  pixel_equal: boolean | null;
  sha256: string | null;
  artifact_id: string | null;
  params: number | null;
  peak_rss_mb: number | null;
  error: string | null;
  details: unknown;
}

export interface Stats {
  total_experiments: number;
  compressions: number;
  decompressions: number;
  benchmark_rows: number;
  verified_ok: number;
  verified_fail: number;
  measured_runs: number;
  avg_ratio: number | null;
  best_ratio: number | null;
  avg_bpsp: number | null;
  total_raw_bytes: number;
  total_artifact_bytes: number;
  bytes_saved: number;
  total_png_bytes: number;
  total_webp_bytes: number;
  avg_enc_ms: number | null;
  avg_dec_ms: number | null;
  by_model: { model: string; n: number; avg_ratio: number; avg_bpsp: number; avg_enc_ms: number; avg_dec_ms: number | null }[];
  series: {
    id: number; created_at: number; model: string; image_name: string; ratio: number; bpsp: number;
    png_bytes: number | null; webp_bytes: number | null; artifact_bytes: number;
  }[];
  recent: Experiment[];
}
