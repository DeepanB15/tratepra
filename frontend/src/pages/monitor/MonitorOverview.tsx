import { Link } from "react-router-dom";
import { Empty, ErrorBox, LifecycleBadge, Loading, fmtAge, fmtNum } from "../../components/common/ui";
import { useAsync } from "../../hooks/useAsync";
import { getOverview, listEvents } from "../../services/monitoring";
import { EventCard } from "../../components/monitor/parts";
import type { WatchRow } from "../../types";
import MonitorNav from "./MonitorNav";

const Stat = ({ label, value }: { label: string; value: number | string }) => (
  <div className="card"><div className="text-xs text-slate-500">{label}</div><div className="text-2xl font-semibold" data-testid={`stat-${label}`}>{value}</div></div>
);
function Mini({ title, rows }: { title: string; rows: WatchRow[] }) {
  return (
    <div className="card">
      <h2 className="mb-2 text-sm font-semibold">{title}</h2>
      {rows.length === 0 ? <p className="text-sm text-slate-500">None right now.</p> : (
        <ul className="divide-y">
          {rows.map((r) => (
            <li key={r.topic_id} className="flex items-center justify-between py-2 text-sm">
              <Link className="text-brand-700 hover:underline" to={`/monitor/trends/${r.topic_id}`}>{r.topic_name}</Link>
              <span className="flex items-center gap-2"><LifecycleBadge value={r.lifecycle} /><span className="text-xs text-slate-500">{r.score_change == null ? "—" : `${r.score_change > 0 ? "+" : ""}${fmtNum(r.score_change)}`}</span></span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function MonitorOverview() {
  const ov = useAsync(getOverview);
  const ev = useAsync(() => listEvents({ limit: 5 }));
  return (
    <div className="space-y-5">
      <h1 className="text-3xl font-semibold tracking-tight">Monitor</h1>
      <MonitorNav />
      {ov.loading && <Loading />}
      {ov.error && <ErrorBox message={ov.error} onRetry={ov.reload} />}
      {ov.data && (
        <>
          {ov.data.followed === 0 && <Empty title="You are not following any trends yet" hint="Open a trend and press Follow, or use the Watchlist tab." />}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Followed" value={ov.data.followed} />
            <Stat label="Active" value={ov.data.active_monitored} />
            <Stat label="New events" value={ov.data.new_events} />
            <Stat label="Important (7d)" value={ov.data.important_events_7d} />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <Mini title="Gaining momentum" rows={ov.data.gaining_momentum} />
            <Mini title="Declining" rows={ov.data.declining} />
          </div>
          <p className="text-xs text-slate-500">
            Trend data from {fmtAge(ov.data.data_freshness.latest_trend_run_completed_at)} · last monitoring cycle:{" "}
            {ov.data.latest_cycle ? `${ov.data.latest_cycle.status} ${fmtAge(ov.data.latest_cycle.started_at)}` : "none yet"}
            {ov.data.latest_cycle?.status === "failed" && <span className="text-rose-700"> — see Settings for the error</span>}
          </p>
        </>
      )}
      <div className="card">
        <div className="mb-1 flex items-center justify-between"><h2 className="text-sm font-semibold">Latest events</h2><Link className="text-xs text-brand-700" to="/monitor/activity">All activity</Link></div>
        {ev.data && ev.data.data.length === 0 && <p className="text-sm text-slate-500">No events yet. Events appear after at least two comparable completed analysis runs.</p>}
        {ev.data && <ul className="divide-y">{ev.data.data.map((e) => <EventCard key={e.id} event={e} />)}</ul>}
      </div>
    </div>
  );
}
