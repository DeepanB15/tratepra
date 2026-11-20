import { Link } from "react-router-dom";
import { Empty, ErrorBox, Loading, SourceStateBadge, fmtDate } from "../components/common/ui";
import { useAsync } from "../hooks/useAsync";
import { getSources } from "../services/research";

export default function Settings() {
  const { data, error, loading, reload } = useAsync(getSources);
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
      <section>
        <h2 className="mb-3 font-semibold">Source connectors</h2>
        {loading && <Loading />}
        {error && <ErrorBox message={error} onRetry={reload} />}
        {data && data.length === 0 && <Empty title="No sources registered" />}
        {data && (
          <ul className="card divide-y">
            {data.map((s) => (
              <li key={s.key} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                <div>
                  <div className="font-medium">{s.name}</div>
                  {s.state === "unavailable" && <div className="text-xs text-amber-700">{s.reason}</div>}
                  {s.last_error && <div className="text-xs text-red-600">Last error: {s.last_error}</div>}
                </div>
                <div className="text-right">
                  <SourceStateBadge state={s.state} />
                  <div className="text-xs text-slate-500">Last run: {fmtDate(s.last_run_at)}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Full run history and counts: <Link className="underline" to="/sources">Source monitoring</Link>. Credentials are configured on the backend via environment variables.</p>
      </section>
    </div>
  );
}
