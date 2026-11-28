import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Empty, ErrorBox, Loading, Pager, fmtDate } from "../components/common/ui";
import { useAsync } from "../hooks/useAsync";
import { getRun, listRuns } from "../services/trends";

const LIMIT = 10;
const STATUS_STYLE: Record<string, string> = {
  completed: "border-emerald-200 text-emerald-700",
  failed: "border-rose-200 text-rose-700",
  running: "border-sky-200 text-sky-700",
  pending: "border-slate-300 text-slate-500",
};

function Kv({ k, v }: { k: string; v: React.ReactNode }) {
  return (<><dt className="text-slate-500">{k}</dt><dd className="text-right tabular-nums">{v ?? "—"}</dd></>);
}

function RunDetailPanel({ id }: { id: string }) {
  const { data: r, error, loading, reload } = useAsync(() => getRun(id), [id]);
  if (loading) return <Loading />;
  if (error || !r) return <ErrorBox message={error ?? "Run not found"} onRetry={reload} />;
  const tq = r.topic_quality ?? {};
  const prep = r.rejection ?? {};
  const reasons = Object.entries((prep.reasons ?? {}) as Record<string, number>).filter(([, n]) => n > 0);
  const outcomes = Object.entries((r.identity?.outcomes ?? {}) as Record<string, number>).filter(([, n]) => n > 0);
  const flaggedTopics = ((tq.topics ?? []) as any[]).filter((x) => x.needs_review);
  return (
    <div className="grid gap-4 bg-stone-50 p-3 text-xs md:grid-cols-3">
      <div>
        <h3 className="mb-1 font-semibold text-slate-800">Documents</h3>
        <dl className="grid grid-cols-2 gap-y-0.5">
          <Kv k="Available" v={r.documents_available} /><Kv k="Processed" v={r.documents_processed} /><Kv k="Rejected" v={r.documents_rejected} />
          <Kv k="Noise" v={`${r.noise_documents}${r.noise_percentage != null ? ` (${r.noise_percentage}%)` : ""}`} />
          {r.input && <><Kv k="Without embedding" v={r.input.without_embedding} /><Kv k="Non-text (excluded)" v={r.input.non_text_documents_in_window} /><Kv k="Future-dated" v={r.input.future_dated} /></>}
        </dl>
        {reasons.length > 0 && (<><h4 className="mb-0.5 mt-2 font-medium">Rejection reasons</h4><ul>{reasons.map(([k, n]) => <li key={k}>{k.replace(/_/g, " ")}: {n}</li>)}</ul></>)}
      </div>
      <div>
        <h3 className="mb-1 font-semibold text-slate-800">Topic quality</h3>
        <dl className="grid grid-cols-2 gap-y-0.5">
          <Kv k="Topics" v={r.topics_discovered} /><Kv k="New / matched" v={`${r.topics_created} / ${r.topics_matched}`} />
          <Kv k="Size min / mean / max" v={tq.topic_size ? `${tq.topic_size.min ?? "—"} / ${tq.topic_size.mean ?? "—"} / ${tq.topic_size.max ?? "—"}` : "—"} />
          <Kv k="Embedding cohesion" v={tq.cohesion?.mean ?? "—"} />
        </dl>
        <p className="mt-1 text-[11px] text-slate-500">Cohesion is embedding-space tightness, not semantic coherence.</p>
        {(tq.run_flags ?? []).map((f: string) => <p key={f} className="mt-1 text-amber-700">⚠ {f}</p>)}
        {(tq.topic_flags ?? []).length > 0 && <p className="mt-1 text-amber-700">⚠ {(tq.topic_flags as any[]).length} topic flag(s): {(tq.topic_flags as any[]).map((f) => f.flag.replace(/_/g, " ")).join(", ")}</p>}
        {flaggedTopics.length > 0 && <p className="mt-1">{flaggedTopics.length} topic(s) need naming review: {flaggedTopics.map((x) => x.name).join("; ")}</p>}
        {tq.source_distribution && <p className="mt-1">Sources: {Object.entries(tq.source_distribution).map(([k, v]) => `${k} ${v}`).join(", ")}</p>}
      </div>
      <div>
        <h3 className="mb-1 font-semibold text-slate-800">Identity &amp; model</h3>
        <dl className="grid grid-cols-2 gap-y-0.5">
          <Kv k="Model" v={r.model_version} /><Kv k="Formula" v={r.formula_version} /><Kv k="Attempts" v={r.attempts} />
          <Kv k="Model changed" v={r.identity ? (r.identity.model_version_changed ? "yes" : "no") : "—"} />
        </dl>
        {outcomes.length > 0 && <p className="mt-1">Identity outcomes: {outcomes.map(([k, n]) => `${k.replace(/_/g, " ")} ${n}`).join(", ")}</p>}
        <details className="mt-2"><summary className="cursor-pointer text-slate-600">Configuration (no secrets)</summary><pre className="mt-1 max-h-48 overflow-auto rounded bg-white p-2 text-[10px]">{JSON.stringify(r.configuration, null, 1)}</pre></details>
        <p className="mt-1 break-all text-[10px] text-slate-400" title="Deterministic fingerprint of documents + window + configuration">run key {r.run_key}</p>
      </div>
      {r.error_message && <div className="md:col-span-3 rounded border border-rose-200 bg-rose-50 p-2 text-rose-800">Error: {r.error_message}</div>}
    </div>
  );
}

export default function Runs() {
  const [sp] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState<string | null>(sp.get("open"));
  const { data, error, loading, reload } = useAsync(() => listRuns({ status: status || undefined, limit: LIMIT, offset }), [status, offset]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Analysis runs</h1>
          <p className="text-xs text-slate-500">Read-only diagnostics. Identical data and configuration on the same day re-use the existing run instead of appending observations.</p>
        </div>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          Status
          <select className="rounded border border-stone-300 bg-white px-2 py-1 text-xs" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
            <option value="">All</option>
            {["completed", "failed", "running", "pending"].map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
      </div>

      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.data.length === 0 && <Empty title="No analysis runs recorded" hint="Run: python -m scripts.run_trend_analysis" />}
      {data && data.data.length > 0 && (
        <div className="overflow-x-auto rounded border border-stone-200">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-stone-200 text-left text-[11px] uppercase text-slate-500">
                <th className="px-2 py-1.5">Status</th><th>Started</th><th>Completed</th>
                <th className="text-right">Docs</th><th className="text-right">Rejected</th><th className="text-right">Noise</th><th className="text-right">Topics</th><th>Model</th><th />
              </tr>
            </thead>
            <tbody>
              {data.data.map((r) => (
                <Fragment key={r.run_id}>
                  <tr className="border-t border-stone-100 align-top">
                    <td className="px-2 py-1.5"><span className={`rounded border px-1.5 py-px text-[11px] font-medium ${STATUS_STYLE[r.status]}`}>{r.status}</span></td>
                    <td className="whitespace-nowrap">{fmtDate(r.started_at)}</td>
                    <td className="whitespace-nowrap">{fmtDate(r.completed_at)}</td>
                    <td className="text-right tabular-nums">{r.documents_processed}</td>
                    <td className="text-right tabular-nums">{r.documents_rejected}</td>
                    <td className="text-right tabular-nums">{r.noise_percentage != null ? `${r.noise_percentage}%` : "—"}</td>
                    <td className="text-right tabular-nums">{r.topics_discovered}</td>
                    <td className="max-w-[10rem] truncate" title={r.model_version}>{r.model_version}</td>
                    <td className="px-2 text-right">
                      <button className="text-brand-700 underline" aria-expanded={open === r.run_id} onClick={() => setOpen(open === r.run_id ? null : r.run_id)}>
                        {open === r.run_id ? "Hide" : "Details"}
                      </button>
                    </td>
                  </tr>
                  {r.error_message && open !== r.run_id && (
                    <tr><td colSpan={9} className="px-2 pb-1.5 text-[11px] text-rose-700">{r.error_message}</td></tr>
                  )}
                  {open === r.run_id && (
                    <tr><td colSpan={9} className="p-0"><RunDetailPanel id={r.run_id} /></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />}
    </div>
  );
}
