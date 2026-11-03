import { ReactNode, useRef, useState } from "react";

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3 animate-fade-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
          <span className="bg-gradient-to-r from-accent-cyan to-accent-violet bg-clip-text text-transparent">{title}</span>
        </h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-400">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function Card({ title, right, children, className = "" }: { title?: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">{title}</h2>}
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, tone = "cyan" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "cyan" | "violet" | "green" | "amber" | "red" }) {
  const tones: Record<string, string> = {
    cyan: "text-accent-cyan", violet: "text-violet-400", green: "text-emerald-400", amber: "text-amber-300", red: "text-red-400",
  };
  return (
    <div className="rounded-xl border border-navy-600/60 bg-navy-900/50 p-4">
      <div className="text-xs uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold ${tones[tone]}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "green" | "red" | "cyan" | "violet" | "amber" }) {
  const t: Record<string, string> = {
    slate: "bg-slate-500/15 text-slate-300", green: "bg-emerald-500/15 text-emerald-300", red: "bg-red-500/15 text-red-300",
    cyan: "bg-cyan-500/15 text-cyan-300", violet: "bg-violet-500/15 text-violet-300", amber: "bg-amber-500/15 text-amber-300",
  };
  return <span className={`badge ${t[tone]}`}>{children}</span>;
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg className="animate-spin" width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity=".25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-slate-400">
        <span className="truncate pr-2">{label || "working…"}</span>
        <span className="font-mono">{pct}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-navy-900">
        <div className="h-full rounded-full bg-gradient-to-r from-accent-cyan to-accent-violet transition-all duration-300" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start justify-between gap-3 rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
      <span>{message}</span>
      {onRetry && (
        <button className="btn-ghost !py-1 text-xs" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-navy-500 p-8 text-center text-sm text-slate-400">{children}</div>;
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 text-sm">
      <span
        className={`relative h-5 w-9 rounded-full transition ${checked ? "bg-accent-cyan" : "bg-navy-500"}`}
        onClick={(e) => {
          e.preventDefault();
          onChange(!checked);
        }}
      >
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${checked ? "left-4" : "left-0.5"}`} />
      </span>
      <span className="text-slate-300">{label}</span>
    </label>
  );
}

export function Dropzone({ accept, onFile, label, disabled }: { accept: string; onFile: (f: File) => void; label: string; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => !disabled && input.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !disabled && input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f && !disabled) onFile(f);
      }}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition ${
        over ? "border-accent-cyan bg-accent-cyan/5" : "border-navy-500 hover:border-accent-cyan/60"
      } ${disabled ? "opacity-50" : ""}`}
    >
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="mb-2 text-accent-cyan">
        <path d="M12 16V4m0 0L7 9m5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div className="text-sm text-slate-300">{label}</div>
      <input
        ref={input}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export function VerifyBadge({ ok, labelOk = "verified", labelBad = "mismatch", labelNone = "not checked" }: { ok: boolean | null | undefined; labelOk?: string; labelBad?: string; labelNone?: string }) {
  if (ok === null || ok === undefined) return <Badge>{labelNone}</Badge>;
  return ok ? <Badge tone="green">✓ {labelOk}</Badge> : <Badge tone="red">✗ {labelBad}</Badge>;
}
