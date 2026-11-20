import { useState } from "react";
import TrendCard from "../components/trends/TrendCard";
import { Empty, ErrorBox, Loading } from "../components/common/ui";
import { useAsync } from "../hooks/useAsync";
import { listTrends } from "../services/trends";

export default function Trends() {
  const [q, setQ] = useState("");
  const [lifecycle, setLifecycle] = useState("");
  const [minSources, setMinSources] = useState(0);

  const { data, error, loading, reload } = useAsync(
    () => listTrends({ q, lifecycle, min_sources: minSources || undefined }),
    [q, lifecycle, minSources]
  );

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Trends</h1>
      <div className="card flex flex-wrap gap-3">
        <input
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          placeholder="Filter by topic…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select className="rounded-lg border border-slate-300 px-3 py-2 text-sm" value={lifecycle} onChange={(e) => setLifecycle(e.target.value)}>
          <option value="">All lifecycles</option>
          <option value="emerging">Emerging</option>
          <option value="growing">Growing</option>
          <option value="peaking">Peaking</option>
          <option value="declining">Declining</option>
        </select>
        <select className="rounded-lg border border-slate-300 px-3 py-2 text-sm" value={minSources} onChange={(e) => setMinSources(Number(e.target.value))}>
          <option value={0}>Any source coverage</option>
          <option value={2}>2+ sources</option>
          <option value={3}>3+ sources</option>
          <option value={4}>4 sources</option>
        </select>
      </div>

      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <Empty title="No trends match" hint="Collect data, then run python -m scripts.run_trend_analysis." />
      )}
      {data && data.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((t) => (
            <TrendCard key={t.topic_id} t={t} />
          ))}
        </div>
      )}
    </div>
  );
}
