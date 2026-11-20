import { Link } from "react-router-dom";
import { Empty, ErrorBox, Loading, fmtDate } from "../components/common/ui";
import { useAsync } from "../hooks/useAsync";
import { listSaved, removeSaved } from "../services/research";

export default function Saved() {
  const { data, error, loading, reload } = useAsync(listSaved);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Saved</h1>
      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.length === 0 && <Empty title="Nothing saved yet" hint="Save research results or trends to find them here." />}
      {data && data.length > 0 && (
        <ul className="card divide-y">
          {data.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <Link
                  className="font-medium text-brand-700 hover:underline"
                  to={s.item_type === "trend" ? `/trends/${s.item_id}` : `/research/${s.item_id}`}
                >
                  {s.title || s.item_id}
                </Link>
                <div className="text-xs text-slate-500">
                  {s.item_type} · saved {fmtDate(s.created_at)}
                </div>
              </div>
              <button className="btn btn-ghost" onClick={() => removeSaved(s.id).then(reload)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
