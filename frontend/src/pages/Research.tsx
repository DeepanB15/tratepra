import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useAsync } from "../hooks/useAsync";
import { useRange } from "../hooks/useRange";
import { createDossier, listDossiers } from "../services/dossiers";
import ResearchView from "../components/research/ResearchView";
import SearchBox from "../components/search/SearchBox";
import { Empty, ErrorBox, Loading } from "../components/common/ui";
import { getHistory, getResearch, searchResearch } from "../services/research";
import type { ResearchResult } from "../types";

export default function Research() {
  const { id } = useParams();
  const location = useLocation();
  const incoming = location.state as { query: string; sources: string[]; range: string } | null;

  const [result, setResult] = useState<ResearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { range } = useRange();
  const [creating, setCreating] = useState(false);
  const [lastRun, setLastRun] = useState<{ sources: string[]; range: string } | null>(null);
  const history = useAsync(getHistory, [result?.research_id]);
  const dossiers = useAsync(() => listDossiers({ limit: 5 }), []);

  const makeDossier = () => {
    if (!result) return;
    setCreating(true);
    createDossier({ query: result.query, time_range: lastRun?.range ?? range, sources: lastRun?.sources ?? result.sources_used })
      .then((d) => navigate(`/dossiers/${d.id}`))
      .catch((e) => { setError(e.message); setCreating(false); });
  };

  const run = (q: string, sources: string[], range: string) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setLastRun({ sources, range });
    searchResearch(q, sources, range)
      .then(setResult)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (id) {
      setLoading(true);
      setError(null);
      getResearch(id)
        .then(setResult)
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    } else if (incoming) {
      run(incoming.query, incoming.sources, incoming.range);
      window.history.replaceState({}, "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Research</h1>
      <SearchBox initialQuery={incoming?.query ?? result?.query ?? ""} loading={loading} suggestions={false} onSubmit={run} />
      {loading && <Loading label="Collecting sources, ranking evidence and writing the answer…" />}
      {error && <ErrorBox message={error} />}
      {result && result.evidence.length === 0 && (
        <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800" role="status">
          Insufficient evidence: no relevant documents were found in the selected sources and time range. Try a longer range or more sources.
        </div>
      )}
      {result && result.evidence.length > 0 && (
        <div className="flex items-center justify-between rounded border border-stone-200 px-3 py-2 text-xs text-slate-600">
          <span>{result.evidence.length} evidence item(s) · time range {lastRun?.range ?? range}</span>
          <button className="rounded border border-slate-800 bg-slate-800 px-3 py-1 text-white disabled:opacity-50" disabled={creating} onClick={makeDossier}>
            {creating ? "Creating…" : "Create dossier from this question"}
          </button>
        </div>
      )}
      {result && <ResearchView result={result} />}
      {!loading && !error && !result && <Empty title="Ask a question to start" hint="Pick one or more sources above." />}
      {!loading && (history.data?.length || dossiers.data?.data.length) ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <section aria-label="Recent questions">
            <h2 className="text-sm font-semibold">Recent questions</h2>
            <ul className="mt-2 space-y-1 text-sm">{(history.data ?? []).slice(0, 6).map((h) => <li key={h.research_id}><Link className="text-brand-700 hover:underline" to={`/research/${h.research_id}`}>{h.query}</Link></li>)}</ul>
          </section>
          <section aria-label="Recent dossiers">
            <h2 className="text-sm font-semibold">Recent dossiers</h2>
            <ul className="mt-2 space-y-1 text-sm">{(dossiers.data?.data ?? []).map((x) => <li key={x.id}><Link className="text-brand-700 hover:underline" to={`/dossiers/${x.id}`}>{x.title}</Link> <span className="text-xs text-slate-400">{x.status}</span></li>)}</ul>
          </section>
        </div>
      ) : null}
    </div>
  );
}
