import { ReactNode, useState } from "react";
import { NavLink } from "react-router-dom";
import { useHealth } from "../hooks";

const NAV: { to: string; label: string; icon: string }[] = [
  { to: "/", label: "Dashboard", icon: "M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10" },
  { to: "/compress", label: "Compress", icon: "M4 7h16M4 12h10M4 17h16" },
  { to: "/benchmark", label: "Benchmark Lab", icon: "M4 20V10m6 10V4m6 16v-7m4 7H2" },
  { to: "/models", label: "Model Lab", icon: "M12 3v4m0 10v4M3 12h4m10 0h4M7 7l2 2m6 6 2 2M17 7l-2 2M9 15l-2 2" },
  { to: "/decompress", label: "Decompress", icon: "M12 4v12m0 0 5-5m-5 5-5-5M4 20h16" },
  { to: "/history", label: "History", icon: "M12 8v5l3 2M3 12a9 9 0 1 0 3-6.7M3 4v4h4" },
  { to: "/about", label: "About & Research", icon: "M12 17v-6m0-4h.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { health, error } = useHealth();
  return (
    <div className="flex min-h-full">
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 transform border-r border-navy-600/70 bg-navy-900/95 p-4 backdrop-blur transition-transform lg:static lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-8 flex items-center gap-3 px-2">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-accent-cyan to-accent-violet text-lg font-black text-navy-950">N</div>
          <div>
            <div className="font-bold leading-tight tracking-tight">NeuroCompress</div>
            <div className="text-[11px] uppercase tracking-widest text-slate-500">neural lossless codec</div>
          </div>
        </div>
        <nav className="space-y-1">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${
                  isActive ? "bg-gradient-to-r from-accent-cyan/20 to-accent-violet/20 text-white ring-1 ring-accent-cyan/30" : "text-slate-400 hover:bg-navy-700/60 hover:text-slate-100"
                }`
              }
            >
              <Icon d={n.icon} />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="absolute inset-x-4 bottom-4 rounded-xl border border-navy-600/60 bg-navy-800/70 p-3 text-xs">
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${health ? "bg-emerald-400 shadow-[0_0_8px_#34d399]" : "bg-red-500"}`} />
            <span className="font-medium text-slate-200">{health ? "Backend online" : "Backend offline"}</span>
          </div>
          <div className="mt-1 text-slate-500">
            {health ? `v${health.version} · ${health.models.length} model${health.models.length === 1 ? "" : "s"}` : "start the API server (see README)"}
          </div>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-navy-600/50 bg-navy-950/80 px-4 py-3 backdrop-blur lg:hidden">
          <button className="btn-ghost !px-3" onClick={() => setOpen(true)} aria-label="Open navigation">
            ☰
          </button>
          <span className="font-semibold">NeuroCompress</span>
        </header>
        {error && (
          <div role="alert" className="border-b border-red-500/30 bg-red-500/10 px-6 py-2 text-sm text-red-200">
            {error}
          </div>
        )}
        <main className="mx-auto w-full max-w-7xl flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
