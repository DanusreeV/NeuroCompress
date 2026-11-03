export function bytes(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 2)} ${u[i]}`;
}
export function num(n: number | null | undefined, d = 2): string {
  return n === null || n === undefined || Number.isNaN(n) ? "—" : n.toFixed(d);
}
export function ms(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n >= 1000 ? `${(n / 1000).toFixed(2)} s` : `${n.toFixed(0)} ms`;
}
export function when(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}
export function short(h: string | null | undefined, n = 12): string {
  return h ? `${h.slice(0, n)}…` : "—";
}
export const COLORS = {
  nc: "#22d3ee",
  ncEff: "#8b5cf6",
  png: "#94a3b8",
  webp: "#fbbf24",
  raw: "#475569",
  grid: "#1e2d52",
  text: "#94a3b8",
};
export const MODEL_COLORS: Record<string, string> = {
  tiny: "#38bdf8",
  small: "#22d3ee",
  base: "#8b5cf6",
  large: "#f472b6",
};
