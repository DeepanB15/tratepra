import { useEffect, useState } from "react";
import { ErrorBox, Loading, fmtAge, fmtDate } from "../../components/common/ui";
import { useAsync } from "../../hooks/useAsync";
import { EVENT_LABELS, getPreferences, getStatus, savePreferences } from "../../services/monitoring";
import type { MonitorPreferences, Severity } from "../../types";
import MonitorNav from "./MonitorNav";

export default function MonitorSettings() {
  const st = useAsync(getStatus);
  const pr = useAsync(getPreferences);
  const [p, setP] = useState<MonitorPreferences | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { if (pr.data) setP(pr.data); }, [pr.data]);
  const save = async () => {
    if (!p) return;
    try { await savePreferences(p); setMsg("Saved."); } catch (e) { setMsg((e as Error).message); }
  };
  const toggle = (t: string) => p && setP({ ...p, muted_event_types: p.muted_event_types.includes(t) ? p.muted_event_types.filter((x) => x !== t) : [...p.muted_event_types, t] });
  return (
    <div className="space-y-5">
      <h1 className="text-3xl font-semibold tracking-tight">Monitoring settings</h1>
      <MonitorNav />
      {pr.error && <ErrorBox message={pr.error} onRetry={pr.reload} />}
      {p && (
        <section className="card space-y-3">
          <h2 className="text-sm font-semibold">Notification preferences</h2>
          <label className="block text-sm">Minimum severity to notify
            <select className="ml-2 rounded border border-stone-300 bg-white px-2 py-1" value={p.min_notification_severity} onChange={(e) => setP({ ...p, min_notification_severity: e.target.value as Severity })}>
              <option value="informational">Informational</option><option value="important">Important</option><option value="critical">Critical</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={p.notify_watchlist_only} onChange={(e) => setP({ ...p, notify_watchlist_only: e.target.checked })} />Only notify for followed trends</label>
          <fieldset><legend className="text-sm">Muted event types (events are still recorded in Activity)</legend>
            <div className="mt-1 grid gap-1 md:grid-cols-2">
              {Object.entries(EVENT_LABELS).filter(([k]) => k !== "monitoring_failure").map(([k, v]) => (
                <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={p.muted_event_types.includes(k)} onChange={() => toggle(k)} />{v}</label>
              ))}
            </div>
          </fieldset>
          <button className="btn btn-primary" onClick={save}>Save preferences</button>
          {msg && <span className="ml-2 text-sm text-slate-600" role="status">{msg}</span>}
        </section>
      )}
      <section className="card space-y-2">
        <h2 className="text-sm font-semibold">Scheduler and jobs</h2>
        {st.loading && <Loading />}
        {st.error && <ErrorBox message={st.error} onRetry={st.reload} />}
        {st.data && (
          <>
            <p className="text-sm" data-testid="scheduler-state">
              Scheduler: <b>{st.data.scheduler.state.replace("_", " ")}</b>
              {st.data.scheduler.enabled ? ` · every ${st.data.scheduler.interval_minutes} min` : " (set MONITORING_SCHEDULER_ENABLED=true on the server to enable; interval is server-configured)"}
              {st.data.scheduler.next_scheduled_at && <> · next {fmtDate(st.data.scheduler.next_scheduled_at)}</>}
            </p>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th>Job</th><th>Last success</th></tr></thead>
              <tbody className="divide-y">
                {Object.entries(st.data.last_successful).map(([j, r]) => (
                  <tr key={j}><td className="py-1 capitalize">{j}</td><td>{r ? `${fmtAge(r.completed_at ?? r.started_at)}${r.duration_ms != null ? ` (${r.duration_ms} ms)` : ""}` : "never"}</td></tr>
                ))}
              </tbody>
            </table>
            {st.data.latest_failures.length > 0 && (
              <div>
                <h3 className="mt-2 text-xs font-semibold text-rose-800">Recent failures</h3>
                <ul className="text-xs text-slate-600">{st.data.latest_failures.map((f) => <li key={f.id}>{f.job_type} · {fmtDate(f.started_at)} · {f.error ?? "no detail"}</li>)}</ul>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
