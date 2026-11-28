import { useState } from "react";
import { Link } from "react-router-dom";
import { Empty, ErrorBox, Loading, Pager, SeverityBadge, fmtDate } from "../../components/common/ui";
import { useAsync } from "../../hooks/useAsync";
import { EVENT_LABELS, listNotifications, markAllRead, patchNotification } from "../../services/monitoring";
import MonitorNav from "./MonitorNav";

const LIMIT = 25;
export default function Notifications() {
  const [status, setStatus] = useState("unread");
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useAsync(() => listNotifications({ status, limit: LIMIT, offset }), [status, offset]);
  const done = (p: Promise<unknown>) => p.then(() => { reload(); window.dispatchEvent(new Event("notifications-changed")); });
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight">Notifications</h1>
      <MonitorNav />
      <div className="flex items-center gap-2">
        {["unread", "all", "dismissed"].map((s) => (
          <button key={s} className={`btn ${status === s ? "btn-primary" : "btn-ghost"}`} onClick={() => { setOffset(0); setStatus(s); }}>{s[0].toUpperCase() + s.slice(1)}</button>
        ))}
        <button className="btn btn-ghost ml-auto" onClick={() => done(markAllRead())}>Mark all read</button>
      </div>
      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.data.length === 0 && <Empty title={status === "unread" ? "You're all caught up" : "Nothing here"} hint="In-app only; nothing is sent by email or push." />}
      {data && data.data.length > 0 && (
        <ul className="card divide-y">
          {data.data.map((n) => (
            <li key={n.id} className={`py-3 ${n.read ? "text-slate-500" : ""}`} data-testid="notification">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge value={n.severity} />
                <span className="text-xs text-slate-500">{EVENT_LABELS[n.event.event_type] ?? n.event.event_type}</span>
                <span className="ml-auto text-xs text-slate-400">{fmtDate(n.created_at)}</span>
              </div>
              <div className="mt-1 text-sm font-medium">{n.event.topic_id ? <Link className="hover:underline" to={`/monitor/trends/${n.event.topic_id}`}>{n.event.title}</Link> : n.event.title}</div>
              {n.event.description && <p className="text-sm">{n.event.description}</p>}
              <div className="mt-1 flex gap-3 text-xs">
                {!n.read && <button className="text-slate-500 hover:text-slate-900" onClick={() => done(patchNotification(n.id, { read: true }))}>Mark read</button>}
                {!n.dismissed && <button className="text-slate-500 hover:text-slate-900" onClick={() => done(patchNotification(n.id, { dismissed: true }))}>Dismiss</button>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {data && <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />}
    </div>
  );
}
