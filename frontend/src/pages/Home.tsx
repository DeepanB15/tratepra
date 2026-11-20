import { Link, useNavigate } from "react-router-dom";
import Icon from "../components/common/Icon";
import { Empty, ErrorBox, Loading, SourceStateBadge, fmtAge, fmtDate, fmtNum } from "../components/common/ui";
import SearchBox from "../components/search/SearchBox";
import TrendCard from "../components/trends/TrendCard";
import { useAsync } from "../hooks/useAsync";
import { getOverview } from "../services/research";

function Stat({ icon, label, value }: { icon: string; label: string; value: string | number }) {
  return (
    <div className="card">
      <Icon name={icon} size={20} className="text-slate-700" />
      <div className="mt-3 text-3xl font-semibold tracking-tight">{value}</div>
      <div className="text-sm text-slate-500">{label}</div>
    </div>
  );
}

export default function Home() {
  const nav = useNavigate();
  const { data, error, loading, reload } = useAsync(getOverview);

  return (
    <div className="mx-auto max-w-5xl space-y-12">
      <section className="pt-6 text-center md:pt-12">
        <h1 className="mx-auto max-w-2xl text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
          Research, discover and track emerging trends.
        </h1>
        <p className="mt-4 text-lg text-slate-500">Search across news, video and community sources, get cited AI insights, and see what's trending.</p>
        <div className="mt-10">
          <SearchBox onSubmit={(q, sources, range) => nav("/research", { state: { query: q, sources, range } })} />
        </div>
      </section>

      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}

      {data && (
        <>
          <section>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <Icon name="trend" /> Trending research
              </h2>
              <Link to="/trends" className="flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900">
                View all <Icon name="arrow" size={14} />
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat icon="doc" label="Research Queries" value={data.research_query_count} />
              <Stat icon="flame" label="Emerging Trends" value={data.emerging_trend_count} />
              <Stat icon="layers" label="Documents Collected" value={data.document_count} />
              <Stat icon="spark" label="Avg. Trend Score" value={data.average_trend_score === null ? "n/a" : fmtNum(data.average_trend_score)} />
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            <div className="card">
              <h3 className="mb-3 font-semibold">Lifecycle distribution</h3>
              {data.active_topic_count === 0 ? (
                <p className="text-sm text-slate-500">No topics yet.</p>
              ) : (
                <ul className="space-y-1.5 text-sm">
                  {Object.entries(data.lifecycle_distribution).map(([k, v]) => (
                    <li key={k} className="flex justify-between">
                      <span className="capitalize">{k}</span>
                      <span className="font-medium">{v}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-xs text-slate-500">{data.active_topic_count} topics, counted from the latest observation of each.</p>
            </div>
            <div className="card">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-semibold">Source freshness</h3>
                <Link to="/sources" className="text-sm text-slate-600 hover:text-slate-900">
                  Monitor
                </Link>
              </div>
              <ul className="space-y-2 text-sm">
                {data.sources.map((s) => (
                  <li key={s.key} className="flex items-center justify-between gap-2">
                    <span>{s.name}</span>
                    <span className="flex items-center gap-2 text-slate-500">
                      {s.document_count} docs · newest {fmtAge(s.latest_document_at)}
                      <SourceStateBadge state={s.state} />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          {data.recent_collections.length > 0 && (
            <section>
              <h2 className="mb-3 text-lg font-semibold">Recent collection activity</h2>
              <ul className="card divide-y divide-stone-100 text-sm">
                {data.recent_collections.map((c, i) => (
                  <li key={`${c.run_id}-${c.source}-${i}`} className="flex flex-wrap justify-between gap-2 py-2">
                    <span>
                      <span className="font-medium">{c.source}</span> · {c.status} · {c.fetched} fetched, {c.accepted} new
                    </span>
                    <span className="text-slate-500">{fmtAge(c.created_at)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            {data.trending.length === 0 ? (
              <Empty title="No trends computed yet" hint="Collect data and run: python -m scripts.run_trend_analysis" />
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {data.trending.map((t) => (
                  <TrendCard key={t.topic_id} t={t} />
                ))}
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-3 text-lg font-semibold">Recent activity</h2>
            {data.recent_activity.length === 0 ? (
              <Empty title="No research yet" hint="Run your first query above." />
            ) : (
              <ul className="card divide-y divide-stone-100">
                {data.recent_activity.map((a) => (
                  <li key={a.research_id} className="flex flex-wrap justify-between gap-2 py-2.5 text-sm">
                    <Link className="font-medium text-brand-700 hover:underline" to={`/research/${a.research_id}`}>
                      {a.query}
                    </Link>
                    <span className="text-slate-500">{fmtDate(a.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
