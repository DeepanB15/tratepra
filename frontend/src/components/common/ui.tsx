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
  emerging: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  growing: "bg-blue-50 text-blue-700 border border-blue-200",
  peaking: "bg-amber-50 text-amber-700 border border-amber-200",
  declining: "bg-rose-50 text-rose-700 border border-rose-200",
};

export function LifecycleBadge({ value }: { value: string | null }) {
  if (!value) return <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">unclassified</span>;
  return (
    <span className={`rounded px-1.5 py-px text-[11px] font-medium ${LIFECYCLE_STYLES[value] ?? "bg-slate-100"}`}>
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

const ACTIVITY_STYLES: Record<string, string> = {
  active: "border-emerald-200 text-emerald-700",
  stale: "border-amber-300 text-amber-700",
  inactive: "border-slate-300 text-slate-500",
};
const ACTIVITY_TITLES: Record<string, string> = {
  active: "Observed in the latest completed analysis run",
  stale: "Not observed in the most recent completed run(s); shown for reference only",
  inactive: "Not observed for several completed runs; hidden from discovery by default",
};

export function ActivityBadge({ value }: { value: string }) {
  return (
    <span title={ACTIVITY_TITLES[value]} className={`rounded border px-1.5 py-px text-[11px] font-medium ${ACTIVITY_STYLES[value] ?? "border-slate-200 text-slate-500"}`}>
      {value}
    </span>
  );
}

export function ScoreValue({ score, withheld, coverage }: { score: number | null; withheld: boolean; coverage?: number | null }) {
  if (score === null || withheld) {
    return (
      <span
        className="text-xs font-medium text-amber-700"
        title={`Score withheld: only ${coverage == null ? "insufficient" : Math.round(coverage * 100) + "%"} of the score's signal weight had data. Missing data is never counted as zero.`}
      >
        withheld
      </span>
    );
  }
  return <span className="font-semibold tabular-nums">{score.toFixed(0)}</span>;
}

export function fmtPct(n: number | null | undefined) {
  return n === null || n === undefined ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(0)}%`;
}

const MOMENTUM_GLYPH: Record<string, string> = { accelerating: "▲", decelerating: "▼", steady: "■", unknown: "–" };
export function MomentumValue({ direction }: { direction: string | null | undefined }) {
  const d = direction ?? "unknown";
  return (
    <span className={d === "accelerating" ? "text-emerald-700" : d === "decelerating" ? "text-rose-700" : "text-slate-500"} title={`Momentum: ${d}`}>
      {MOMENTUM_GLYPH[d] ?? "–"} {d === "unknown" ? "n/a" : d}
    </span>
  );
}

export function Pager({ offset, limit, total, onChange }: { offset: number; limit: number; total: number | null; onChange: (offset: number) => void }) {
  if (total === null || total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <nav className="flex items-center justify-between text-xs text-slate-600" aria-label="Pagination">
      <span>
        {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </span>
      <span className="flex items-center gap-2">
        <button className="rounded border border-stone-200 bg-white px-2 py-1 disabled:opacity-40" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Previous
        </button>
        <span>
          Page {page} / {pages}
        </span>
        <button className="rounded border border-stone-200 bg-white px-2 py-1 disabled:opacity-40" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          Next
        </button>
      </span>
    </nav>
  );
}

const SEV_STYLE: Record<string, string> = {
  critical: "border-rose-300 bg-rose-50 text-rose-800",
  important: "border-amber-300 bg-amber-50 text-amber-800",
  informational: "border-stone-200 bg-white text-slate-600",
};
export function SeverityBadge({ value }: { value: string }) {
  return <span className={`rounded border px-1.5 py-0.5 text-[11px] font-medium capitalize ${SEV_STYLE[value] ?? SEV_STYLE.informational}`}>{value}</span>;
}
