import { useState } from "react";
import { Empty, ErrorBox, Loading, Pager } from "../../components/common/ui";
import { EventCard } from "../../components/monitor/parts";
import { useAsync } from "../../hooks/useAsync";
import { EVENT_LABELS, listEvents } from "../../services/monitoring";
import MonitorNav from "./MonitorNav";

const LIMIT = 25;
export default function Activity() {
  const [type, setType] = useState("");
  const [severity, setSeverity] = useState("");
  const [state, setState] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useAsync(() => listEvents({ event_type: type, severity, state, limit: LIMIT, offset }), [type, severity, state, offset]);
  const sel = "rounded border border-stone-300 bg-white px-2 py-1 text-sm";
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight">Intelligence activity</h1>
      <MonitorNav />
      <div className="flex flex-wrap gap-2">
        <select className={sel} aria-label="Event type" value={type} onChange={(e) => { setOffset(0); setType(e.target.value); }}>
          <option value="">All types</option>{Object.entries(EVENT_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className={sel} aria-label="Severity" value={severity} onChange={(e) => { setOffset(0); setSeverity(e.target.value); }}>
          <option value="">Any severity</option><option value="critical">Critical</option><option value="important">Important</option><option value="informational">Informational</option>
        </select>
        <select className={sel} aria-label="State" value={state} onChange={(e) => { setOffset(0); setState(e.target.value); }}>
          <option value="">Any state</option><option value="new">New</option><option value="read">Read</option><option value="dismissed">Dismissed</option><option value="archived">Archived</option>
        </select>
      </div>
      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.data.length === 0 && <Empty title="No events match" hint="Events are created only from comparable, completed analysis runs." />}
      {data && data.data.length > 0 && <ul className="card divide-y">{data.data.map((e) => <EventCard key={e.id} event={e} onChange={reload} />)}</ul>}
      {data && <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />}
    </div>
  );
}
