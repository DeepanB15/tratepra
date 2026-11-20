import { Link } from "react-router-dom";
import { Empty, ErrorBox, Loading, fmtDate } from "../components/common/ui";
import { useAsync } from "../hooks/useAsync";
import { getHistory } from "../services/research";

export default function History() {
  const { data, error, loading, reload } = useAsync(getHistory);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">History</h1>
      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.length === 0 && <Empty title="No research history" hint="Your past queries will appear here." />}
      {data && data.length > 0 && (
        <ul className="card divide-y">
          {data.map((h) => (
            <li key={h.research_id} className="py-3">
              <Link className="font-medium text-brand-700 hover:underline" to={`/research/${h.research_id}`}>
                {h.query}
              </Link>
              <div className="text-xs text-slate-500">
                {fmtDate(h.created_at)} · sources: {h.sources.join(", ")}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
