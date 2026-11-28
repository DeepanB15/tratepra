import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ActivityBadge, ErrorBox, LifecycleBadge, Loading, fmtDate, fmtNum } from "../../components/common/ui";
import { EventCard, FollowButton } from "../../components/monitor/parts";
import { useAsync } from "../../hooks/useAsync";
import { getTrendHistory, getTrendMonitoring, patchWatch } from "../../services/monitoring";

export default function TrendMonitor() {
  const { id = "" } = useParams();
  const m = useAsync(() => getTrendMonitoring(id), [id]);
  const h = useAsync(() => getTrendHistory(id), [id]);
  const [note, setNote] = useState<string | null>(null);
  if (m.loading) return <Loading />;
  if (m.error || !m.data) return <ErrorBox message={m.error ?? "Not found"} onRetry={m.reload} />;
  const d = m.data;
  const l = d.latest;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start gap-3">
        <div>
          <Link to="/monitor/watchlist" className="text-xs text-slate-500 hover:underline">← Watchlist</Link>
          <h1 className="text-3xl font-semibold tracking-tight">{d.topic_name}</h1>
          <p className="text-xs text-slate-500">{d.terms.join(" · ")}</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <FollowButton topicId={d.topic_id} followed={d.followed} onChange={() => m.reload()} />
          <Link className="btn btn-ghost" to={`/trends/${d.topic_id}`}>Trend page</Link>
          {d.dossier?.has_content && <Link className="btn btn-ghost" to={`/dossiers/${d.dossier.id}`}>Dossier</Link>}
        </div>
      </div>
      {l && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {[["Score", fmtNum(l.trend_score)], ["Growth", l.growth == null ? "—" : `${fmtNum(l.growth)}%`], ["Documents", l.document_volume ?? "—"], ["Sources", l.sources ?? "—"]].map(([k, v]) => (
            <div className="card" key={k as string}><div className="text-xs text-slate-500">{k}</div><div className="text-xl font-semibold">{v}</div></div>
          ))}
          <div className="card"><div className="text-xs text-slate-500">State</div><div className="mt-1 flex gap-1"><LifecycleBadge value={l.lifecycle} /><ActivityBadge value={d.activity_state} /></div></div>
        </div>
      )}
      {d.watch && (
        <section className="card space-y-2">
          <h2 className="text-sm font-semibold">Your note</h2>
          <textarea className="w-full rounded border border-stone-300 p-2 text-sm" rows={2} aria-label="Note" defaultValue={d.watch.user_note} onChange={(e) => setNote(e.target.value)} />
          <button className="btn btn-ghost" disabled={note === null} onClick={() => patchWatch(d.topic_id, { user_note: note ?? "" }).then(() => setNote(null))}>Save note</button>
        </section>
      )}
      <section className="card">
        <h2 className="mb-2 text-sm font-semibold">Observation history</h2>
        {h.data && h.data.length === 0 && <p className="text-sm text-slate-500">No completed observations.</p>}
        {h.data && h.data.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500"><tr><th>Observed</th><th>Score</th><th>Growth</th><th>Docs</th><th>Lifecycle</th><th>Formula</th></tr></thead>
            <tbody className="divide-y">
              {[...h.data].reverse().map((s) => (
                <tr key={s.observation_id}>
                  <td className="py-1">{fmtDate(s.observed_at)}</td><td>{fmtNum(s.trend_score)}</td><td>{s.growth == null ? "—" : `${fmtNum(s.growth)}%`}</td><td>{s.document_volume ?? "—"}</td>
                  <td><LifecycleBadge value={s.lifecycle} />{s.lifecycle_changed && <span className="ml-1 text-xs text-amber-700">changed</span>}</td>
                  <td className="text-xs text-slate-500">{s.formula_version}{s.comparable_with_previous === false && <span className="ml-1 text-amber-700" title="Not compared with the previous snapshot">not comparable</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="card">
        <h2 className="mb-1 text-sm font-semibold">Events ({d.event_total})</h2>
        {d.events.length === 0 ? <p className="text-sm text-slate-500">No events for this trend yet.</p> : <ul className="divide-y">{d.events.map((e) => <EventCard key={e.id} event={e} showTopic={false} onChange={() => m.reload()} />)}</ul>}
      </section>
    </div>
  );
}
