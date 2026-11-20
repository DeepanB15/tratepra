import { useState } from "react";
import { saveItem } from "../../services/research";
import type { ResearchResult } from "../../types";
import { fmtDate } from "../common/ui";

// Turns [n] markers into links to the matching evidence URL.
function Cited({ text, result }: { text: string; result: ResearchResult }) {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[(\d+)\]$/);
        if (!m) return <span key={i}>{p}</span>;
        const ev = result.evidence[Number(m[1]) - 1];
        if (!ev) return null;
        return (
          <a
            key={i}
            href={ev.url ?? "#"}
            target="_blank"
            rel="noreferrer"
            title={ev.title}
            className="mx-0.5 align-super text-xs font-semibold text-brand-600 hover:underline"
          >
            [{m[1]}]
          </a>
        );
      })}
    </>
  );
}

const STATUS_STYLE: Record<string, string> = {
  ok: "bg-emerald-100 text-emerald-700",
  skipped: "bg-slate-100 text-slate-600",
  unavailable: "bg-slate-100 text-slate-600",
};

function Fact({ label, value }: { label: string; value: number | string | undefined }) {
  return (
    <div>
      <div className="text-xl font-semibold">{value ?? "—"}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}

export function TransparencyPanel({ result }: { result: ResearchResult }) {
  const t = result.transparency ?? {};
  if (!t.sources_searched && t.sources_searched !== 0) return null;
  const c = t.claims ?? {};
  return (
    <div className="card">
      <h3 className="mb-3 font-semibold">How this answer was built</h3>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
        <Fact label="sources searched" value={t.sources_searched} />
        <Fact label="results collected" value={t.results_collected} />
        <Fact label="new after dedupe" value={t.accepted} />
        <Fact label="duplicates removed" value={t.duplicates_removed} />
        <Fact label="outside time range" value={t.out_of_window} />
        <Fact label="evidence used" value={t.evidence_selected} />
      </div>
      <p className="mt-3 text-xs text-slate-500">
        {c.claims_total !== undefined && `${c.claims_verified}/${c.claims_total} statements verified against cited evidence. `}
        {t.timing_ms && `Time: collection ${t.timing_ms.collection} ms, retrieval ${t.timing_ms.retrieval} ms, synthesis ${t.timing_ms.synthesis} ms.`}
      </p>
    </div>
  );
}

export default function ResearchView({ result }: { result: ResearchResult }) {
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const total = Object.values(result.source_distribution).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{result.query}</h2>
            <p className="text-xs text-slate-500">
              {fmtDate(result.created_at)} · model: {result.model} · {(result.execution_ms / 1000).toFixed(1)}s
            </p>
          </div>
          <button
            className="btn btn-ghost"
            disabled={saved}
            onClick={() =>
              saveItem("research", result.research_id, result.query)
                .then(() => setSaved(true))
                .catch((e) => setErr(e.message))
            }
          >
            {saved ? "Saved ✓" : "Save"}
          </button>
        </div>
        {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
        {result.degraded && (
          <p className="mt-3 rounded bg-amber-50 p-2 text-sm text-amber-800">
            The language model was unavailable; showing an extractive summary instead of a synthesized answer.
          </p>
        )}
        <p className="mt-4 whitespace-pre-line leading-relaxed">
          <Cited text={result.answer} result={result} />
        </p>
      </div>

      {result.key_findings.length > 0 && (
        <div className="card">
          <h3 className="mb-2 font-semibold">Key findings</h3>
          <ul className="list-disc space-y-1 pl-5">
            {result.key_findings.map((f, i) => (
              <li key={i}>
                <Cited text={f} result={result} />
              </li>
            ))}
          </ul>
        </div>
      )}

      <TransparencyPanel result={result} />

      {result.unverified_claims.length > 0 && (
        <div className="card border-amber-200">
          <h3 className="mb-1 font-semibold">Removed: could not be verified</h3>
          <p className="mb-2 text-xs text-slate-500">
            These statements from the draft answer were left out because they lacked a valid, openable citation that covers them.
            This is a text-overlap check, not proof of correctness.
          </p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
            {result.unverified_claims.map((c, i) => (
              <li key={i}>
                {c.text} <span className="text-xs text-amber-700">({c.reason})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card">
          <h3 className="mb-2 font-semibold">Source status</h3>
          <ul className="space-y-1 text-sm">
            {Object.entries(result.source_status).map(([k, s]) => (
              <li key={k} className="flex flex-wrap items-center gap-2">
                <span className="w-28 font-medium">{k}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLE[s.status] ?? "bg-red-100 text-red-700"}`}>
                  {s.status}
                </span>
                {s.error && <span className="text-xs text-slate-500">{s.error}</span>}
              </li>
            ))}
          </ul>
        </div>
        <div className="card">
          <h3 className="mb-2 font-semibold">Source distribution (evidence)</h3>
          <div className="space-y-2">
            {Object.entries(result.source_distribution).map(([k, v]) => (
              <div key={k} className="text-sm">
                <div className="flex justify-between">
                  <span>{k}</span>
                  <span>{v}</span>
                </div>
                <div className="h-2 rounded bg-slate-100">
                  <div className="h-2 rounded bg-brand-500" style={{ width: `${(v / total) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="mb-2 font-semibold">Evidence</h3>
        <ol className="space-y-2">
          {result.evidence.map((e, i) => (
            <li key={e.document_id} className="flex gap-3 text-sm">
              <span className="w-6 shrink-0 text-right font-semibold text-slate-400">{i + 1}</span>
              <div className="min-w-0">
                {e.url ? (
                  <a href={e.url} target="_blank" rel="noreferrer" className="font-medium text-brand-700 hover:underline">
                    {e.title}
                  </a>
                ) : (
                  <span className="font-medium">{e.title}</span>
                )}
                <div className="text-xs text-slate-500">
                  {e.source} · {fmtDate(e.published_at)} · relevance {e.relevance?.toFixed(0)} {e.cited ? "· cited" : ""}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>

      {result.related_topics.length > 0 && (
        <div className="card">
          <h3 className="mb-2 font-semibold">Related topics</h3>
          <div className="flex flex-wrap gap-2">
            {result.related_topics.map((t) => (
              <span key={t} className="rounded-full bg-slate-100 px-3 py-1 text-sm">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
