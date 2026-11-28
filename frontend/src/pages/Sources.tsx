import { Empty, ErrorBox, Loading, SourceStateBadge, fmtAge, fmtDate } from "../components/common/ui";
import { useAsync } from "../hooks/useAsync";
import { getSourceLogs, getSources } from "../services/research";
import { getDiscoveryOverview } from "../services/trends";
import { Link } from "react-router-dom";

export default function Sources() {
  const sources = useAsync(getSources);
  const logs = useAsync(() => getSourceLogs(50));
  const ov = useAsync(getDiscoveryOverview);
  const list = sources.data ?? [];
  const count = (st: string) => list.filter((s) => s.state === st).length;
  const available = list.filter((s) => s.state === "operational" || s.state === "configured").length;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Sources &amp; data health</h1>
        <p className="mt-1 text-sm text-slate-500">
          State is derived from real collection runs. "configured" means credentials exist but no successful run has confirmed them.
        </p>
      </div>

      <section aria-label="Data health" className="grid grid-cols-2 divide-x divide-stone-200 rounded border border-stone-200 text-sm sm:grid-cols-5">
        {[
          ["Configured sources", list.length],
          ["Available", available],
          ["Unavailable", count("unavailable")],
          ["Failing", count("failing")],
          ["Documents stored", list.reduce((n, s) => n + s.document_count, 0)],
        ].map(([k, v]) => (
          <div key={k as string} className="px-3 py-2">
            <div className="text-[11px] uppercase tracking-wide text-slate-500">{k}</div>
            <div className="text-xl font-semibold tabular-nums">{sources.data ? v : "—"}</div>
          </div>
        ))}
        <p className="col-span-full border-t border-stone-200 px-3 py-2 text-xs text-slate-600">
          Trend analysis:{" "}
          {ov.data
            ? ov.data.data_freshness.latest_successful_analysis_at
              ? `last completed ${fmtAge(ov.data.data_freshness.latest_successful_analysis_at)}${ov.data.data_freshness.overdue ? " (overdue)" : ""}, ${ov.data.documents_analyzed ?? 0} documents analysed.`
              : "no completed analysis yet."
            : ov.error ?? "…"}{" "}
          <Link to="/runs" className="underline">Analysis runs</Link>
        </p>
      </section>

      <section>
        {sources.loading && <Loading />}
        {sources.error && <ErrorBox message={sources.error} onRetry={sources.reload} />}
        {sources.data && sources.data.length === 0 && <Empty title="No sources registered" />}
        {sources.data && (
          <div className="grid gap-4 md:grid-cols-2">
            {sources.data.map((s) => (
              <div key={s.key} className="card text-sm">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold">{s.name}</h2>
                  <SourceStateBadge state={s.state} />
                </div>
                {s.reason && s.state === "unavailable" && <p className="mt-2 text-xs text-amber-700">{s.reason}</p>}
                {s.last_error && <p className="mt-2 text-xs text-red-600">Last error: {s.last_error}</p>}
                <dl className="mt-3 grid grid-cols-2 gap-y-1 text-slate-600">
                  <dt>Documents stored</dt>
                  <dd className="text-right font-medium text-slate-900">{s.document_count}</dd>
                  <dt>Newest document</dt>
                  <dd className="text-right">{fmtAge(s.latest_document_at)}</dd>
                  <dt>Last run</dt>
                  <dd className="text-right">{fmtDate(s.last_run_at)}</dd>
                  <dt>Last run fetched / new</dt>
                  <dd className="text-right">
                    {s.last_fetched ?? "—"} / {s.last_accepted ?? "—"}
                  </dd>
                  <dt>Last run duration</dt>
                  <dd className="text-right">{s.last_duration_ms === null ? "—" : `${s.last_duration_ms} ms`}</dd>
                </dl>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Collection log</h2>
        {logs.loading && <Loading />}
        {logs.error && <ErrorBox message={logs.error} onRetry={logs.reload} />}
        {logs.data && logs.data.length === 0 && <Empty title="No collection runs yet" hint="Run a research query to collect data." />}
        {logs.data && logs.data.length > 0 && (
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-slate-500">
                  <th className="py-1">When</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th className="text-right">Fetched</th>
                  <th className="text-right">New</th>
                  <th className="text-right">Dupes</th>
                  <th className="text-right">Out of range</th>
                  <th className="text-right">Rejected</th>
                </tr>
              </thead>
              <tbody>
                {logs.data.map((l, i) => (
                  <tr key={`${l.run_id}-${l.source}-${i}`} className="border-t border-stone-100 align-top">
                    <td className="py-1.5 whitespace-nowrap">{fmtAge(l.created_at)}</td>
                    <td>{l.source}</td>
                    <td>
                      {l.status}
                      {l.error && <div className="max-w-xs text-xs text-red-600">{l.error}</div>}
                    </td>
                    <td className="text-right">{l.fetched}</td>
                    <td className="text-right">{l.accepted}</td>
                    <td className="text-right">{l.duplicates}</td>
                    <td className="text-right">{l.out_of_window}</td>
                    <td className="text-right">{l.rejected}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
