import { useState } from "react";
import { Link } from "react-router-dom";
import { ActivityBadge, Empty, ErrorBox, LifecycleBadge, Loading, Pager, fmtNum } from "../../components/common/ui";
import { useAsync } from "../../hooks/useAsync";
import { listWatchlist, patchWatch, unfollow } from "../../services/monitoring";
import MonitorNav from "./MonitorNav";

const LIMIT = 25;
export default function Watchlist() {
  const [q, setQ] = useState("");
  const [priority, setPriority] = useState("");
  const [enabled, setEnabled] = useState("");
  const [sort, setSort] = useState("priority");
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useAsync(
    () => listWatchlist({ q, priority, enabled: enabled === "" ? undefined : enabled === "true", sort, limit: LIMIT, offset }),
    [q, priority, enabled, sort, offset],
  );
  const sel = "rounded border border-stone-300 bg-white px-2 py-1 text-sm";
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight">Watchlist</h1>
      <MonitorNav />
      <div className="flex flex-wrap gap-2">
        <input className={sel} placeholder="Search followed trends" aria-label="Search" value={q} onChange={(e) => { setOffset(0); setQ(e.target.value); }} />
        <select className={sel} aria-label="Priority" value={priority} onChange={(e) => { setOffset(0); setPriority(e.target.value); }}>
          <option value="">Any priority</option><option value="high">High</option><option value="normal">Normal</option><option value="low">Low</option>
        </select>
        <select className={sel} aria-label="Monitoring" value={enabled} onChange={(e) => { setOffset(0); setEnabled(e.target.value); }}>
          <option value="">Enabled and paused</option><option value="true">Enabled</option><option value="false">Paused</option>
        </select>
        <select className={sel} aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="priority">Priority</option><option value="score">Score</option><option value="change">Change</option><option value="added">Recently added</option>
        </select>
      </div>
      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.data.length === 0 && <Empty title="Nothing on your watchlist" hint="Follow a trend from its page to monitor it. Following never deletes history." />}
      {data && data.data.length > 0 && (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-stone-200 text-left text-xs text-slate-500">
              <tr><th className="p-2">Trend</th><th>Score</th><th>Change</th><th>Lifecycle</th><th>Activity</th><th>Priority</th><th /></tr>
            </thead>
            <tbody className="divide-y">
              {data.data.map((r) => (
                <tr key={r.topic_id} className={r.monitoring_enabled ? "" : "text-slate-400"} data-testid="watch-row">
                  <td className="p-2"><Link className="text-brand-700 hover:underline" to={`/monitor/trends/${r.topic_id}`}>{r.topic_name}</Link>{!r.monitoring_enabled && <span className="ml-2 text-xs">paused</span>}</td>
                  <td>{fmtNum(r.latest_score)}</td>
                  <td title={r.score_change_note ?? undefined}>{r.score_change == null ? "—" : `${r.score_change > 0 ? "+" : ""}${fmtNum(r.score_change)}`}</td>
                  <td><LifecycleBadge value={r.lifecycle} /></td>
                  <td><ActivityBadge value={r.activity_state} /></td>
                  <td>
                    <select className="rounded border border-stone-200 bg-white px-1 text-xs" aria-label={`Priority for ${r.topic_name}`} value={r.priority} onChange={(e) => patchWatch(r.topic_id, { priority: e.target.value }).then(reload)}>
                      <option value="high">high</option><option value="normal">normal</option><option value="low">low</option>
                    </select>
                  </td>
                  <td className="space-x-2 whitespace-nowrap pr-2 text-right text-xs">
                    <button className="text-slate-500 hover:text-slate-900" onClick={() => patchWatch(r.topic_id, { monitoring_enabled: !r.monitoring_enabled }).then(reload)}>{r.monitoring_enabled ? "Pause" : "Resume"}</button>
                    <button className="text-slate-500 hover:text-rose-700" onClick={() => unfollow(r.topic_id).then(reload)}>Unfollow</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />}
    </div>
  );
}
