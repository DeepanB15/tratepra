import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createDossier } from "../services/dossiers";
import { ContributionChart, HistoryVolumeChart, ScoreHistoryChart, VolumeChart } from "../components/charts/Charts";
import { ActivityBadge, ErrorBox, LifecycleBadge, Loading, MomentumValue, ScoreValue, fmtAge, fmtDate, fmtNum, fmtPct } from "../components/common/ui";
import { useAsync } from "../hooks/useAsync";
import { saveItem } from "../services/research";
import { getTrend, getTrendHistory } from "../services/trends";
import { getTrendMonitoring } from "../services/monitoring";
import { FollowButton } from "../components/monitor/parts";

function Stat({ label, children, how }: { label: string; children: React.ReactNode; how: string }) {
  return (
    <div className="rounded border border-stone-200 p-3">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tabular-nums">{children}</div>
      <p className="mt-1 text-[11px] leading-snug text-slate-500">{how}</p>
    </div>
  );
}

const IDENTITY_TEXT: Record<string, string> = {
  matched: "Matched an existing topic from earlier runs (one-to-one centroid match), so its history carries over.",
  new: "No sufficiently similar stored topic: registered as a new topic.",
  potential_split: "Similar to a stored topic that another new topic claimed: may be a part that broke off. Registered as new, not silently matched.",
  potential_merge: "Matched an existing topic but also resembles another stored topic: it may have absorbed it.",
  uncertain: "Resembles a stored topic, but not closely enough to match: identity uncertain, registered as new.",
};

export default function TrendDetail() {
  const { id = "" } = useParams();
  const detail = useAsync(() => getTrend(id), [id]);
  const history = useAsync(() => getTrendHistory(id), [id]);
  const mon = useAsync(() => getTrendMonitoring(id), [id]);
  const [saved, setSaved] = useState(false);
  const navigate = useNavigate();
  const [investigating, setInvestigating] = useState(false);
  const [investigateError, setInvestigateError] = useState<string | null>(null);
  const investigate = () => {
    setInvestigating(true);
    setInvestigateError(null);
    createDossier({ topic_id: id, time_range: "30d" })
      .then((d) => navigate(`/dossiers/${d.id}`))
      .catch((e) => { setInvestigateError(e.message); setInvestigating(false); });
  };

  if (detail.loading) return <Loading />;
  if (detail.error || !detail.data) return <ErrorBox message={detail.error ?? "Trend not found"} onRetry={detail.reload} />;
  const t = detail.data;
  const cov = t.coverage ?? {};
  const vols = t.weekly_volumes ?? [];
  const contributions = t.explanation?.contributions ?? [];
  const hist = history.data ?? [];
  const identity = t.identity?.outcome as string | undefined;

  return (
    <div className="space-y-4">
      <Link to="/" className="text-xs text-slate-500 hover:underline">← Discover</Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t.topic_name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <LifecycleBadge value={t.lifecycle} />
            <ActivityBadge value={t.activity_state} />
            {t.needs_review && <span className="rounded border border-slate-300 px-1.5 py-px text-[11px]" title={t.review_reasons.join("; ")}>needs review</span>}
            <span title={fmtDate(t.last_observed_at)}>Last observed {fmtAge(t.last_observed_at)}</span>
            <span>First seen {fmtDate(t.first_seen_at)}</span>
          </div>
        </div>
        <div className="flex gap-2">
        {mon.data && <FollowButton topicId={id} followed={mon.data.followed} />}
        {mon.data?.followed && <Link className="rounded border border-stone-300 bg-white px-3 py-1 text-xs" to={`/monitor/trends/${id}`}>Monitoring</Link>}
        <button className="rounded border border-slate-800 bg-slate-800 px-3 py-1 text-xs text-white disabled:opacity-50" disabled={investigating} onClick={investigate}>
          {investigating ? "Opening…" : "Investigate this trend"}
        </button>
        <button className="rounded border border-stone-300 bg-white px-3 py-1 text-xs disabled:opacity-50" disabled={saved} onClick={() => saveItem("trend", t.topic_id, t.topic_name).then(() => setSaved(true))}>
          {saved ? "Saved ✓" : "Save"}
        </button>
        </div>
      </div>
      {investigateError && <ErrorBox message={investigateError} />}

      {t.activity_state !== "active" && (
        <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800" role="status">
          This topic is <b>{t.activity_state}</b>: it was not observed in the most recent completed analysis run(s). Figures below are from its last observation.
        </div>
      )}

      <section className="rounded border border-stone-200 p-3" aria-label="Why this ranking">
        <h2 className="text-sm font-semibold">Why this ranking</h2>
        <p className="mt-1 text-sm text-slate-700">{t.explanation?.summary ?? "No explanation available."}</p>
        {t.explanation?.acceleration && (
          <p className="mt-1 text-xs text-slate-600"><b className="font-medium">Trajectory ({t.explanation.acceleration.label.replace(/_/g, " ")}):</b> {t.explanation.acceleration.text}</p>
        )}
      </section>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Trend score" how={t.score_withheld ? "Withheld: too little of the score's signal weight had data. Missing signals are never counted as zero." : t.previous_score != null ? `Weighted blend of available signals (0–100). Previous run: ${fmtNum(t.previous_score)}.` : "Weighted blend of available signals (0–100)."}>
          <ScoreValue score={t.trend_score} withheld={t.score_withheld} coverage={cov.signal_weight_coverage} />
        </Stat>
        <Stat label="Score coverage" how={`Share of score weight that had data (minimum ${cov.min_coverage != null ? Math.round(cov.min_coverage * 100) + "%" : "n/a"}). ${cov.sources_observed ?? 0} of ${Math.max(cov.sources_available ?? 0, cov.sources_observed ?? 0)} sources observed.`}>
          {cov.signal_weight_coverage != null ? `${Math.round(cov.signal_weight_coverage * 100)}%` : "—"}
        </Stat>
        <Stat label="Growth" how={vols.length >= 2 ? `Latest window vs previous: ${vols[vols.length - 2]} → ${vols[vols.length - 1]} documents.${t.growth_flag && t.growth_flag !== "ok" ? ` Note: ${t.growth_flag.replace(/_/g, " ")}.` : ""}` : "Needs at least two windows of history."}>
          {fmtPct(t.growth_pct)}
        </Stat>
        <Stat label="Momentum" how={t.momentum_pp != null ? `Change in growth rate across windows: ${t.momentum_pp > 0 ? "+" : ""}${t.momentum_pp.toFixed(1)} percentage points.` : "Needs at least three windows of history."}>
          <MomentumValue direction={t.momentum_direction} />
        </Stat>
        <Stat label="Document volume" how="Documents in the latest weekly window, out of all documents assigned to this topic across the lookback.">
          {t.document_volume ?? "—"} <span className="text-xs font-normal text-slate-500">/ {t.topic_size ?? "—"} total</span>
        </Stat>
        <Stat label="Novelty" how="Distance from the nearest topic stored in earlier runs (higher = more unlike anything seen before).">{fmtNum(t.signals.novelty, 0)}</Stat>
        <Stat label="Name confidence" how="Share of this topic's documents containing a term from its name, blended with term distinctiveness. A measurement of the name, not of topic quality.">
          {t.name_confidence != null ? `${Math.round(t.name_confidence * 100)}%` : "—"}
        </Stat>
        <Stat label="Sources" how={Object.entries(t.source_distribution).map(([k, v]) => `${k} ${v}`).join(" · ") || "No source breakdown stored."}>
          {Object.keys(t.source_distribution).length}
        </Stat>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="rounded border border-stone-200 p-3" aria-label="Signal contributions">
          <h2 className="mb-1 text-sm font-semibold">Signal contributions</h2>
          <ContributionChart rows={contributions} />
          <table className="mt-2 w-full text-xs">
            <thead>
              <tr className="text-left text-[11px] uppercase text-slate-500"><th className="py-1">Signal</th><th>Value</th><th>Weight</th><th className="text-right">Points</th></tr>
            </thead>
            <tbody>
              {contributions.map((c) => (
                <tr key={c.signal} className="border-t border-stone-100">
                  <td className="py-1">{c.label}</td>
                  <td>{c.value === null ? <span className="text-slate-400">no data</span> : fmtNum(c.value)}</td>
                  <td>{c.weight}</td>
                  <td className="text-right">{c.points === null ? "—" : fmtNum(c.points, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(t.explanation?.missing ?? []).length > 0 && (
            <ul className="mt-2 space-y-0.5 text-[11px] text-slate-500">
              {t.explanation.missing!.map((m) => <li key={m.signal}><b className="font-medium">{m.label}:</b> {m.reason}</li>)}
            </ul>
          )}
        </section>

        <section className="rounded border border-stone-200 p-3" aria-label="Historical activity">
          <h2 className="mb-1 text-sm font-semibold">Historical activity</h2>
          {history.loading && <Loading />}
          {history.error && <ErrorBox message={history.error} onRetry={history.reload} />}
          {history.data && hist.length <= 1 && <p className="mb-2 text-[11px] text-slate-500">Only {hist.length} stored observation(s) so far; the per-window volume below comes from the latest run.</p>}
          <VolumeChart values={vols} label="Documents per weekly window (latest run, oldest → newest)" />
          {hist.length > 1 && (
            <>
              <div className="mt-2 text-xs text-slate-500">Documents in the latest window, per analysis run</div>
              <HistoryVolumeChart points={hist.map((h) => ({ label: new Date(h.window_end).toLocaleDateString(), volume: h.document_volume, legacy: h.legacy }))} />
              <ScoreHistoryChart points={hist.map((h) => ({ label: new Date(h.window_end).toLocaleDateString(), score: h.trend_score }))} />
              <p className="text-[11px] text-slate-500">Gaps in the score line are runs where the score was withheld.</p>
            </>
          )}
        </section>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="rounded border border-stone-200 p-3" aria-label="Representative articles">
          <h2 className="mb-1 text-sm font-semibold">Representative articles</h2>
          <p className="mb-2 text-[11px] text-slate-500">Closest to the topic centroid, not simply the newest.</p>
          {t.representative_documents.length === 0 && <p className="text-xs text-slate-500">No documents linked.</p>}
          <ul className="space-y-2 text-sm">
            {t.representative_documents.map((d) => (
              <li key={d.id}>
                {d.url ? <a className="font-medium text-brand-700 hover:underline" href={d.url} target="_blank" rel="noreferrer">{d.title}</a> : d.title}
                <div className="text-[11px] text-slate-500">{d.source} · {fmtDate(d.published_at)}</div>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded border border-stone-200 p-3" aria-label="Terms and related topics">
          <h2 className="mb-1 text-sm font-semibold">Key terms &amp; related topics</h2>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {t.terms.map((x) => <span key={x} className="rounded border border-stone-200 px-1.5 py-px text-xs text-slate-700">{x}</span>)}
          </div>
          {t.related_topic_details.length === 0 && <p className="text-xs text-slate-500">No related topics yet.</p>}
          <ul className="space-y-1 text-sm">
            {t.related_topic_details.map((r) => (
              <li key={r.topic_id}>
                <Link className="text-brand-700 hover:underline" to={`/trends/${r.topic_id}`}>{r.name}</Link>
                <span className="ml-2 text-[11px] text-slate-500" title="Cosine similarity of topic centroids">similarity {r.similarity.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="rounded border border-stone-200 p-3 text-xs text-slate-600" aria-label="Model and run information">
        <h2 className="mb-1 text-sm font-semibold text-slate-900">Model &amp; last run</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5">
          <dt>Topic model</dt><dd>{t.model_version ?? "—"}</dd>
          <dt>Score formula</dt><dd>{t.formula_version ?? "—"}</dd>
          <dt>Last run</dt>
          <dd>{t.last_run ? <Link className="text-brand-700 hover:underline" to={`/runs?open=${t.last_run.run_id}`}>{t.last_run.status} · {fmtDate(t.last_run.completed_at)} · {t.last_run.documents_processed} docs</Link> : "Recorded before run tracking existed (legacy observation)"}</dd>
          <dt>Identity</dt><dd>{identity ? IDENTITY_TEXT[identity] ?? identity : "—"}</dd>
          {t.review_reasons.length > 0 && (<><dt>Review notes</dt><dd>{t.review_reasons.join("; ")}</dd></>)}
        </dl>
      </section>
    </div>
  );
}
