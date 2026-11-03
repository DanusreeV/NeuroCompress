import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { Health, Job } from "./types";

export interface JobState<T> {
  status: "idle" | "running" | "done" | "error";
  progress: number;
  message: string;
  result: T | null;
  error: string | null;
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
export const errText = (e: unknown): string => (e instanceof Error ? e.message : String(e));

/** Starts a backend job and polls /api/jobs/{id} until it finishes. */
export function useJob<T>() {
  const idle: JobState<T> = { status: "idle", progress: 0, message: "", result: null, error: null };
  const [state, setState] = useState<JobState<T>>(idle);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const run = useCallback(async (start: () => Promise<{ job_id: string }>): Promise<T | null> => {
    setState({ status: "running", progress: 0, message: "submitting…", result: null, error: null });
    try {
      const { job_id } = await start();
      for (;;) {
        const j: Job<T> = await api.job<T>(job_id);
        if (!alive.current) return null;
        if (j.status === "done") {
          setState({ status: "done", progress: 1, message: "done", result: j.result, error: null });
          return j.result;
        }
        if (j.status === "failed") {
          setState({ status: "error", progress: j.progress, message: "", result: null, error: j.error?.message ?? j.message });
          return null;
        }
        setState((s) => ({ ...s, status: "running", progress: j.progress, message: j.message }));
        await sleep(250);
      }
    } catch (e) {
      if (alive.current) setState({ status: "error", progress: 0, message: "", result: null, error: errText(e) });
      return null;
    }
  }, []);

  const reset = useCallback(() => setState(idle), []); // eslint-disable-line react-hooks/exhaustive-deps
  return { state, run, reset };
}

export function useHealth(intervalMs = 8000) {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const h = await api.health();
        if (!stop) {
          setHealth(h);
          setError(null);
        }
      } catch (e) {
        if (!stop) {
          setHealth(null);
          setError(e instanceof ApiError ? e.message : errText(e));
        }
      }
    };
    tick();
    const t = setInterval(tick, intervalMs);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [intervalMs]);
  return { health, error };
}

/** Loads data once (and again when `reload` is called). Never substitutes fake data on failure. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let stop = false;
    setLoading(true);
    fn()
      .then((d) => {
        if (!stop) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (!stop) setError(errText(e));
      })
      .finally(() => {
        if (!stop) setLoading(false);
      });
    return () => {
      stop = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}
