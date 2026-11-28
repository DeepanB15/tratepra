import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArticleBadge, ClaimBadge, QualityCard, RoleBadge, claimLabel } from "../components/dossier/parts";
import { Empty, ErrorBox, Loading, Pager, fmtAge, fmtDate } from "../components/common/ui";
import { getDossier, listDossierClaims, listDossierEvidence, refreshDossier } from "../services/dossiers";
import type { Dossier as DossierT, DossierClaim, DossierEvidenceItem } from "../types";

const TABS = ["Dossier", "Evidence", "Claims"] as const;
type Tab = (typeof TABS)[number];
const PAGE = 20;

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section className="rounded border border-stone-200 p-3" aria-label={title} data-testid={`section-${id}`}>
      <h2 className="text-sm font-semibold">{title}</h2>
      <div className="mt-2 text-sm text-slate-700">{children}</div>
    </section>
  );
}

function EvidenceCard({ e }: { e: DossierEvidenceItem }) {
  return (
    <li className="rounded border border-stone-200 p-2.5" data-testid="evidence-item">
      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
        <RoleBadge role={e.role} />
        <ArticleBadge status={e.article_status} />
        <span>{e.publisher}</span>
        <span>· {e.published_at ? new Date(e.published_at).toLocaleDateString() : "undated"}</span>
        <span>· {e.source}</span>
      </div>
      <a className="mt-1 block text-sm font-medium text-brand-700 hover:underline" href={e.url ?? "#"} target="_blank" rel="noreferrer">
        [{e.rank}] {e.title}
      </a>
      {e.excerpt && (
        <p className="mt-1 text-xs text-slate-600">
          <span className="text-slate-400">{e.excerpt_basis === "article" ? "Article excerpt: " : "Feed summary: "}</span>
          {e.excerpt}
        </p>
      )}
      <p className="mt-1 text-[11px] text-slate-400">{e.role_reason}</p>
    </li>
  );
}

function EvidenceExplorer({ id }: { id: string }) {
  const [role, setRole] = useState("");
  const [publisher, setPublisher] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ items: DossierEvidenceItem[]; total: number | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    listDossierEvidence(id, {
      role: role || undefined, publisher: publisher || undefined,
      date_from: from ? new Date(from).toISOString() : undefined, date_to: to ? new Date(to + "T23:59:59").toISOString() : undefined,
      limit: PAGE, offset,
    }).then((r) => setData({ items: r.data, total: r.total })).catch((e) => setError(e.message));
  }, [id, role, publisher, from, to, offset]);

  const input = "rounded border border-stone-300 bg-white px-2 py-1 text-xs";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2 text-xs">
        <label>Role <select aria-label="Role" className={input} value={role} onChange={(e) => { setRole(e.target.value); setOffset(0); }}>
          <option value="">All</option><option value="supporting">Supporting</option><option value="contradictory">Contradictory</option><option value="context">Context</option>
        </select></label>
        <label>Publisher <input aria-label="Publisher" className={input} value={publisher} onChange={(e) => { setPublisher(e.target.value); setOffset(0); }} placeholder="e.g. example.com" /></label>
        <label>From <input aria-label="From date" type="date" className={input} value={from} onChange={(e) => { setFrom(e.target.value); setOffset(0); }} /></label>
        <label>To <input aria-label="To date" type="date" className={input} value={to} onChange={(e) => { setTo(e.target.value); setOffset(0); }} /></label>
        {data?.total != null && <span className="text-slate-500">{data.total} item(s)</span>}
      </div>
      {error && <ErrorBox message={error} />}
      {!data && !error && <Loading />}
      {data && data.items.length === 0 && <Empty title="No evidence matches these filters" />}
      <ul className="space-y-2">{data?.items.map((e) => <EvidenceCard key={e.id} e={e} />)}</ul>
      <Pager offset={offset} limit={PAGE} total={data?.total ?? null} onChange={setOffset} />
    </div>
  );
}

function ClaimView({ id }: { id: string }) {
  const [status, setStatus] = useState("");
  const [data, setData] = useState<DossierClaim[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    listDossierClaims(id, { status: status || undefined, limit: 100 }).then((r) => setData(r.data)).catch((e) => setError(e.message));
  }, [id, status]);
  return (
    <div className="space-y-3">
      <p className="rounded border border-stone-200 bg-stone-50 px-3 py-2 text-xs text-slate-600">
        Each statement is checked against the excerpt it cites using a lexical-overlap heuristic. "Supported" means the cited text shares most of the statement's content words;
        it does not prove the statement is true, and a correct paraphrase can be marked unverified. Contradictions are found only when evidence uses explicit negation or decline wording.
      </p>
      <label className="text-xs">Status <select aria-label="Claim status" className="rounded border border-stone-300 bg-white px-2 py-1 text-xs" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All</option>
        {["supported", "partially_supported", "contradicted", "unverified", "insufficient_evidence"].map((s) => <option key={s} value={s}>{claimLabel(s as never)}</option>)}
      </select></label>
      {error && <ErrorBox message={error} />}
      {!data && !error && <Loading />}
      {data && data.length === 0 && <Empty title="No claims" hint="No statements were generated, or none match this filter." />}
      <ul className="space-y-2">
        {data?.map((c) => (
          <li key={c.id} className="rounded border border-stone-200 p-2.5" data-testid="claim-item">
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
              <span>#{c.claim_no}</span><ClaimBadge status={c.status} /><span>{c.claim_type}</span><span>· {c.section.replace("_", " ")}</span>
              <span>· {c.source_coverage} publisher(s)</span>{c.overlap != null && <span>· word overlap {Math.round(c.overlap * 100)}%</span>}
            </div>
            <p className="mt-1 text-sm">{c.text}</p>
            <p className="mt-1 text-xs text-slate-500">{c.explanation}</p>
            <p className="mt-1 text-[11px] text-slate-400">{c.supporting_evidence_ids.length} supporting · {c.contradictory_evidence_ids.length} contradicting evidence item(s)</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Dossier() {
  const { id = "" } = useParams();
  const [d, setD] = useState<DossierT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Dossier");
  const [busy, setBusy] = useState(false);
  const timer = useRef<number>();

  const load = useCallback(() => {
    getDossier(id).then((x) => { setD(x); setError(null); }).catch((e) => setError(e.message));
  }, [id]);
  useEffect(() => { load(); return () => window.clearTimeout(timer.current); }, [load]);
  useEffect(() => {  // poll only while a generation is in progress
    if (d?.processing.status === "running" || d?.processing.status === "pending") timer.current = window.setTimeout(load, 2000);
    return () => window.clearTimeout(timer.current);
  }, [d, load]);

  const refresh = () => {
    setBusy(true);
    refreshDossier(id).then(setD).catch((e) => setError(e.message)).finally(() => setBusy(false));
  };

  if (error && !d) return <ErrorBox message={error} onRetry={load} />;
  if (!d) return <Loading />;
  const p = d.processing;
  const s = d.sections;
  const running = p.status === "running" || p.status === "pending";
  const dims = d.evidence_quality.dimensions ?? {};

  return (
    <div className="space-y-4">
      <Link to={d.topic_id ? `/trends/${d.topic_id}` : "/research"} className="text-xs text-slate-500 hover:underline">← {d.topic_id ? "Trend" : "Research"}</Link>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight" data-testid="dossier-title">{d.title}</h1>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
            <span>Time range {d.time_range}</span>
            <span title={fmtDate(d.generated_at)}>{d.generated_at ? `Generated ${fmtAge(d.generated_at)}` : "Not generated yet"}</span>
            <span>{d.evidence_count} evidence · {d.claim_count} claims</span>
            {d.evidence_quality.summary && <span>{d.evidence_quality.summary}</span>}
          </div>
        </div>
        <button className="rounded border border-stone-300 bg-white px-3 py-1 text-xs disabled:opacity-50" disabled={running || busy} onClick={refresh}>
          {running ? "Generating…" : "Refresh dossier"}
        </button>
      </header>

      {running && <div className="rounded border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800" role="status">
        {p.has_content ? "Regenerating. The previous result is shown until the new one completes." : "Generating this dossier: retrieving evidence and checking claims. This page updates automatically."}
      </div>}
      {p.status === "failed" && <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800" role="alert">
        The last generation failed{p.error ? `: ${p.error}` : ""}.{p.has_content ? " The previous result is still shown." : ""} Use Refresh dossier to retry.
      </div>}
      {p.interrupted && <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">This generation appears interrupted (no completion recorded). Refresh to retry.</div>}

      {!p.has_content ? (!running && <Empty title="No dossier content yet" hint="Generation has not completed successfully." />) : (<>
        <nav className="flex gap-1 border-b border-stone-200" role="tablist">
          {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`px-3 py-1.5 text-xs ${tab === t ? "border-b-2 border-slate-800 font-semibold" : "text-slate-500"}`}>{t}</button>)}
        </nav>

        {tab === "Evidence" && <EvidenceExplorer id={d.id} />}
        {tab === "Claims" && <ClaimView id={d.id} />}
        {tab === "Dossier" && (
          <div className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" aria-label="Evidence quality">
              {Object.entries(dims).map(([k, v]) => <QualityCard key={k} name={k} dim={v} />)}
            </div>
            <p className="text-[11px] text-slate-400">{d.evidence_quality.note}</p>

            <Section id="overview" title="A. Executive overview">
              <p>{s.overview?.text}</p>
              {(s.overview?.claims_total ?? 0) > 0 && <p className="mt-1 text-xs text-slate-500">{s.overview?.claims_flagged ?? 0} of {s.overview?.claims_total} generated statement(s) were not verified and are excluded here; see Claims.</p>}
            </Section>
            <Section id="developments" title="B. Key developments">
              {(s.key_developments?.items ?? []).length === 0 ? <p className="text-slate-500">None found.</p> : (
                <ol className="space-y-1.5">{s.key_developments!.items.map((i) => (
                  <li key={i.document_id}><span className="text-xs text-slate-500">{i.date ?? "undated"} · {i.publisher}</span><div><b className="font-medium">[{i.citation}] {i.title}</b></div><div className="text-xs text-slate-600">{i.summary}</div></li>
                ))}</ol>)}
            </Section>
            <Section id="supporting" title="C. Supporting evidence">
              {(s.supporting_evidence?.items ?? []).length === 0 ? <p className="text-slate-500">No evidence is linked to a verified claim. Open the Evidence tab for everything retrieved.</p> :
                <ul className="space-y-2">{s.supporting_evidence!.items.map((e) => <EvidenceCard key={e.id ?? e.document_id} e={e} />)}</ul>}
            </Section>
            <Section id="contradictory" title="D. Contradictory evidence">
              {s.contradictory_evidence?.text ? <p>{s.contradictory_evidence.text}</p> :
                <ul className="space-y-2">{s.contradictory_evidence?.items.map((e) => <EvidenceCard key={e.id ?? e.document_id} e={e} />)}</ul>}
              <p className="mt-1 text-[11px] text-slate-400">{s.contradictory_evidence?.method}</p>
            </Section>
            <Section id="entities" title="E. Key entities">
              {(s.key_entities?.items ?? []).length === 0 ? <p className="text-slate-500">No entities were found in the retrieved documents.</p> :
                <ul className="flex flex-wrap gap-1.5">{s.key_entities!.items.map((e) => <li key={e.name} className="rounded border border-stone-200 px-2 py-0.5 text-xs">{e.name} <span className="text-slate-400">· {e.documents} doc(s), {e.publishers} publisher(s)</span></li>)}</ul>}
            </Section>
            <Section id="gaps" title="F. Evidence gaps">
              {(s.evidence_gaps?.items ?? []).length === 0 ? <p className="text-slate-500">No gaps detected by the configured rules.</p> :
                <ul className="list-disc space-y-1 pl-5">{s.evidence_gaps!.items.map((g) => <li key={g.code}>{g.text}</li>)}</ul>}
            </Section>
            <Section id="questions" title="G. Research questions">
              {(s.research_questions?.items ?? []).length === 0 ? <p className="text-slate-500">None suggested.</p> :
                <ul className="list-disc space-y-1 pl-5">{s.research_questions!.items.map((q) => <li key={q}>{q}</li>)}</ul>}
              <p className="mt-1 text-[11px] text-slate-400">{s.research_questions?.note}</p>
            </Section>
            <ul className="list-disc space-y-0.5 pl-5 text-[11px] text-slate-400">{d.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          </div>
        )}
      </>)}
    </div>
  );
}
