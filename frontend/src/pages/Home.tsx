import { Link } from "react-router-dom";
import { Empty, ErrorBox, Loading, fmtAge } from "../components/common/ui";
import TrendRow from "../components/trends/TrendRow";
import { useAsync } from "../hooks/useAsync";
import { getDiscoveryOverview, searchTrends, type TrendQuery } from "../services/trends";

const SECTIONS: { key: string; title: string; hint: string; query: TrendQuery; link: string }[] = [
  { key: "emerging", title: "Emerging signals", hint: "Lifecycle: emerging — new activity with little history", query: { lifecycle: "emerging", limit: 5 }, link: "?lifecycle=emerging" },
  { key: "rising", title: "Rising trends", hint: "Lifecycle: growing — sustained growth", query: { lifecycle: "growing", limit: 5 }, link: "?lifecycle=growing" },
  { key: "accelerating", title: "Accelerating trends", hint: "Momentum accelerating across recent windows", query: { momentum: "accelerating", sort: "momentum", limit: 5 }, link: "?momentum=accelerating&sort=momentum" },
  { key: "declining", title: "Declining trends", hint: "Lifecycle: declining", query: { lifecycle: "declining", limit: 5 }, link: "?lifecycle=declining" },
  { key: "new", title: "Newly discovered topics", hint: "First seen in the last 14 days", query: { is_new: true, sort: "recent", limit: 5 }, link: "?is_new=true&sort=recent" },
];

function Metric({ label, value, hint, to }: { label: string; value: string | number; hint?: string; to?: string }) {
  const body = (
    <div className="px-3 py-2" title={hint}>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
    </div>
  );
  return to ? <Link to={to} className="block hover:bg-stone-50">{body}</Link> : body;
}

function Section({ s }: { s: (typeof SECTIONS)[number] }) {
  const { data, error, loading, reload } = useAsync(() => searchTrends(s.query), []);
  return (
    <section aria-labelledby={`h-${s.key}`} className="rounded border border-stone-200">
      <div className="flex items-baseline justify-between border-b border-stone-200 px-3 py-2">
        <div>
          <h2 id={`h-${s.key}`} className="text-sm font-semibold">{s.title}</h2>
          <p className="text-[11px] text-slate-500">{s.hint}</p>
        </div>
        <Link to={`/trends${s.link}`} className="text-xs text-slate-600 hover:underline">
          {data?.total != null ? `View all (${data.total})` : "View all"}
        </Link>
      </div>
      <div className="px-3">
        {loading && <Loading />}
        {error && <div className="py-3"><ErrorBox message={error} onRetry={reload} /></div>}
        {data && data.data.length === 0 && <p className="py-4 text-xs text-slate-500">No active trends in this category.</p>}
        {data && data.data.length > 0 && <ul className="divide-y divide-stone-100">{data.data.map((t) => <TrendRow key={t.topic_id} t={t} />)}</ul>}
      </div>
    </section>
  );
}

export default function Home() {
  const ov = useAsync(getDiscoveryOverview);
  const o = ov.data;
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Discover</h1>
        <p className="text-xs text-slate-500">Emerging topics ranked by measurable signals. Every score links to the evidence behind it.</p>
      </div>

      {ov.loading && <Loading />}
      {ov.error && <ErrorBox message={ov.error} onRetry={ov.reload} />}

      {o && (
        <>
          <div className="grid grid-cols-2 divide-x divide-y divide-stone-200 rounded border border-stone-200 sm:grid-cols-5 sm:divide-y-0">
            <Metric label="Active trends" value={o.total_active_trends} hint="Observed in the latest completed analysis run" to="/trends" />
            <Metric label="Emerging" value={o.emerging_trends} to="/trends?lifecycle=emerging" />
            <Metric label="Rising" value={o.rising_trends} hint="Lifecycle 'growing'" to="/trends?lifecycle=growing" />
            <Metric label="Score withheld" value={o.withheld_score_trends} hint="Active trends without enough signal coverage for a numeric score" to="/trends?score_withheld=true" />
            <Metric label="Latest analysis" value={fmtAge(o.data_freshness.latest_successful_analysis_at)} hint={o.documents_analyzed != null ? `${o.documents_analyzed} documents analysed` : undefined} to="/runs" />
          </div>

          {o.latest_successful_run === null && (
            <Empty title="No completed analysis yet" hint="Collect data, then run: python -m scripts.run_trend_analysis (add --dry-run to preview without saving)." />
          )}
          {o.latest_run_status === "failed" && (
            <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800" role="status">
              The most recent analysis run failed{o.latest_run?.error_message ? `: ${o.latest_run.error_message}` : ""}. Results below are from the last completed run. <Link className="underline" to="/runs">Inspect runs</Link>
            </div>
          )}
          {o.data_freshness.overdue && o.latest_successful_run !== null && (
            <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800" role="status">
              The latest completed analysis is older than {o.data_freshness.overdue_after_days} days; trends may not reflect recent activity.
            </div>
          )}
          {o.stale_trends > 0 && (
            <p className="text-xs text-slate-500">
              {o.stale_trends} stale and {o.inactive_trends} inactive topic(s) are hidden from these lists. <Link className="underline" to="/trends?activity_state=stale">Show stale</Link>
            </p>
          )}
        </>
      )}

      {(!o || o.latest_successful_run !== null) && <div className="space-y-4">{SECTIONS.map((s) => <Section key={s.key} s={s} />)}</div>}
    </div>
  );
}
