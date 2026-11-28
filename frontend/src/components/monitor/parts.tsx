import { useState } from "react";
import { Link } from "react-router-dom";
import { EVENT_LABELS, follow, setEventState, unfollow } from "../../services/monitoring";
import type { TrendEventItem } from "../../types";
import { SeverityBadge, fmtDate } from "../common/ui";

export function FollowButton({ topicId, followed, onChange }: { topicId: string; followed: boolean; onChange?: (f: boolean) => void }) {
  const [on, setOn] = useState(followed);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const toggle = async () => {
    setBusy(true);
    setErr(null);
    try {
      if (on) await unfollow(topicId);
      else await follow(topicId);
      setOn(!on);
      onChange?.(!on);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button className={`btn ${on ? "btn-ghost" : "btn-primary"}`} onClick={toggle} disabled={busy} aria-pressed={on} title={on ? "Stop monitoring (history is kept)" : "Monitor this trend"}>
        {on ? "Following" : "Follow"}
      </button>
      {err && <span className="text-xs text-rose-700">{err}</span>}
    </span>
  );
}

/** One event. The explanation is stored deterministic text built from stored values, never regenerated in the browser. */
export function EventCard({ event, onChange, showTopic = true }: { event: TrendEventItem; onChange?: (e: TrendEventItem) => void; showTopic?: boolean }) {
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const act = async (state: string) => {
    try {
      onChange?.(await setEventState(event.id, state));
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  return (
    <li className={`py-3 ${event.state === "dismissed" ? "opacity-60" : ""}`} data-testid="event-card">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge value={event.severity} />
        <span className="text-xs text-slate-500">{EVENT_LABELS[event.event_type] ?? event.event_type}</span>
        {event.state === "new" && <span className="text-[11px] font-medium text-brand-700">new</span>}
        <span className="ml-auto text-xs text-slate-400">{fmtDate(event.detected_at)}</span>
      </div>
      <div className="mt-1 text-sm font-medium">
        {showTopic && event.topic_id ? <Link className="hover:underline" to={`/monitor/trends/${event.topic_id}`}>{event.title}</Link> : event.title}
      </div>
      {event.description && <p className="text-sm text-slate-600">{event.description}</p>}
      <div className="mt-1 flex gap-3 text-xs">
        <button className="text-slate-500 hover:text-slate-900" onClick={() => setOpen((o) => !o)} aria-expanded={open}>{open ? "Hide details" : "Why was this flagged?"}</button>
        {event.state !== "read" && event.state !== "dismissed" && <button className="text-slate-500 hover:text-slate-900" onClick={() => act("read")}>Mark read</button>}
        {event.state !== "dismissed" ? <button className="text-slate-500 hover:text-slate-900" onClick={() => act("dismissed")}>Dismiss</button> : <button className="text-slate-500 hover:text-slate-900" onClick={() => act("new")}>Restore</button>}
      </div>
      {err && <div className="text-xs text-rose-700">{err}</div>}
      {open && (
        <div className="mt-2 rounded border border-stone-200 p-3 text-sm">
          <p className="whitespace-pre-line text-slate-700">{event.explanation ?? "No explanation stored."}</p>
          {event.evidence.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">
              {event.evidence.map((d) => (
                <li key={d.document_id}>{d.url ? <a className="text-brand-700 hover:underline" href={d.url} target="_blank" rel="noreferrer">{d.title}</a> : d.title}</li>
              ))}
            </ul>
          )}
          <div className="mt-2 text-[11px] text-slate-400">Detection {event.detection_version} · deterministic rule, not a statistical test unless stated</div>
        </div>
      )}
    </li>
  );
}
