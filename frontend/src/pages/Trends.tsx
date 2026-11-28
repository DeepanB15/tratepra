import { useSearchParams } from "react-router-dom";
import { Empty, ErrorBox, Loading, Pager } from "../components/common/ui";
import TrendRow from "../components/trends/TrendRow";
import { useAsync } from "../hooks/useAsync";
import { searchTrends } from "../services/trends";

const LIMIT = 20;
const SORTS = [
  ["score", "Trend score"],
  ["growth", "Growth"],
  ["momentum", "Momentum"],
  ["documents", "Documents"],
  ["recent", "Last observed"],
  ["name", "Name"],
];
const sel = "rounded border border-stone-300 bg-white px-2 py-1 text-xs";

export default function Trends() {
  const [sp, setSp] = useSearchParams();
  const get = (k: string, d = "") => sp.get(k) ?? d;
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(sp);
    if (v === "" || v === undefined) n.delete(k);
    else n.set(k, v);
    n.delete("offset");
    setSp(n, { replace: true });
  };
  const offset = Number(get("offset", "0")) || 0;
  const q = get("q");
  const f = {
    q: q || undefined,
    lifecycle: get("lifecycle") || undefined,
    activity_state: get("activity_state", "active"),
    momentum: get("momentum") || undefined,
    min_sources: Number(get("min_sources", "0")) || undefined,
    min_score: get("min_score") ? Number(get("min_score")) : undefined,
    max_age_days: get("max_age_days") ? Number(get("max_age_days")) : undefined,
    is_new: get("is_new") === "true" ? true : undefined,
    score_withheld: get("score_withheld") === "true" ? true : undefined,
    sort: get("sort", "score"),
    order: (get("order", "desc") as "asc" | "desc"),
    limit: LIMIT,
    offset,
  };
  const { data, error, loading, reload } = useAsync(() => searchTrends(f), [sp.toString()]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Trends</h1>
        <p className="text-xs text-slate-500">Active trends by default. Stale and inactive topics are hidden unless selected.</p>
      </div>

      <form className="flex flex-wrap items-end gap-2 rounded border border-stone-200 p-2" role="search" onSubmit={(e) => e.preventDefault()}>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          Search
          <input className={`${sel} w-44`} placeholder="Topic name or term" value={q} onChange={(e) => set("q", e.target.value)} />
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          Lifecycle
          <select className={sel} value={get("lifecycle")} onChange={(e) => set("lifecycle", e.target.value)}>
            <option value="">All</option>
            {["emerging", "growing", "peaking", "declining"].map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          Activity
          <select className={sel} value={f.activity_state} onChange={(e) => set("activity_state", e.target.value)}>
            {["active", "stale", "inactive", "all"].map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          Momentum
          <select className={sel} value={get("momentum")} onChange={(e) => set("momentum", e.target.value)}>
            <option value="">Any</option>
            {["accelerating", "steady", "decelerating", "unknown"].map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          Sources
          <select className={sel} value={get("min_sources", "0")} onChange={(e) => set("min_sources", e.target.value === "0" ? "" : e.target.value)}>
            <option value="0">Any</option>
            {[2, 3, 4].map((x) => <option key={x} value={x}>{x}+</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          Min score
          <input className={`${sel} w-16`} type="number" min={0} max={100} value={get("min_score")} onChange={(e) => set("min_score", e.target.value)} />
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          Observed within
          <select className={sel} value={get("max_age_days")} onChange={(e) => set("max_age_days", e.target.value)}>
            <option value="">Any time</option>
            {[7, 14, 30].map((x) => <option key={x} value={x}>{x} days</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          Sort
          <select className={sel} value={f.sort} onChange={(e) => set("sort", e.target.value)}>
            {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <button type="button" className={sel} onClick={() => set("order", f.order === "desc" ? "asc" : "desc")} aria-label={`Sort order ${f.order}`}>
          {f.order === "desc" ? "↓ desc" : "↑ asc"}
        </button>
        {sp.toString() && (
          <button type="button" className="text-xs text-slate-500 underline" onClick={() => setSp({}, { replace: true })}>
            Reset
          </button>
        )}
      </form>

      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.data.length === 0 && <Empty title="No trends match these filters" hint="Relax a filter, or run: python -m scripts.run_trend_analysis" />}
      {data && data.data.length > 0 && (
        <div className="rounded border border-stone-200 px-3">
          <ul className="divide-y divide-stone-100">{data.data.map((t) => <TrendRow key={t.topic_id} t={t} />)}</ul>
        </div>
      )}
      {data && (
        <Pager
          offset={offset}
          limit={LIMIT}
          total={data.total}
          onChange={(o) => {
            const n = new URLSearchParams(sp);
            o === 0 ? n.delete("offset") : n.set("offset", String(o));
            setSp(n);
          }}
        />
      )}
    </div>
  );
}
