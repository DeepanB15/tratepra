export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-8 text-slate-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600" />
      {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
      {message}
      {onRetry && (
        <button className="ml-3 underline" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center">
      <div className="font-medium text-slate-700">{title}</div>
      {hint && <div className="mt-1 text-sm text-slate-500">{hint}</div>}
    </div>
  );
}

const LIFECYCLE_STYLES: Record<string, string> = {
  emerging: "bg-emerald-100 text-emerald-700",
  growing: "bg-blue-100 text-blue-700",
  peaking: "bg-amber-100 text-amber-700",
  declining: "bg-rose-100 text-rose-700",
};

export function LifecycleBadge({ value }: { value: string | null }) {
  if (!value) return <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">unclassified</span>;
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${LIFECYCLE_STYLES[value] ?? "bg-slate-100"}`}>
      {value}
    </span>
  );
}

export function fmtDate(s: string | null | undefined) {
  return s ? new Date(s).toLocaleString() : "—";
}

export function fmtNum(n: number | null | undefined, digits = 1) {
  return n === null || n === undefined ? "—" : n.toFixed(digits);
}

const STATE_STYLES: Record<string, string> = {
  operational: "bg-emerald-100 text-emerald-700",
  configured: "bg-sky-100 text-sky-700",
  failing: "bg-red-100 text-red-700",
  unavailable: "bg-slate-100 text-slate-600",
};
const STATE_TITLES: Record<string, string> = {
  operational: "Last collection run succeeded",
  configured: "Credentials present, not yet verified by a successful run",
  failing: "Last collection run failed",
  unavailable: "Not configured or not usable",
};

export function SourceStateBadge({ state }: { state: string }) {
  return (
    <span title={STATE_TITLES[state]} className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATE_STYLES[state] ?? "bg-slate-100"}`}>
      {state}
    </span>
  );
}

/** "3 h ago" style freshness; "never" when there is no timestamp. */
export function fmtAge(s: string | null | undefined, now: number = Date.now()) {
  if (!s) return "never";
  const mins = Math.max(0, Math.round((now - new Date(s).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 60 * 48) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} d ago`;
}
