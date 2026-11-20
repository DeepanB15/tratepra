import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import ResearchView from "../components/research/ResearchView";
import SearchBox from "../components/search/SearchBox";
import { Empty, ErrorBox, Loading } from "../components/common/ui";
import { getResearch, searchResearch } from "../services/research";
import type { ResearchResult } from "../types";

export default function Research() {
  const { id } = useParams();
  const location = useLocation();
  const incoming = location.state as { query: string; sources: string[]; range: string } | null;

  const [result, setResult] = useState<ResearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = (q: string, sources: string[], range: string) => {
    setLoading(true);
    setError(null);
    setResult(null);
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
      {result && <ResearchView result={result} />}
      {!loading && !error && !result && <Empty title="Ask a question to start" hint="Pick one or more sources above." />}
    </div>
  );
}
