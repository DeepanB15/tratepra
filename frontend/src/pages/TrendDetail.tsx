import { useState } from "react";
import { useParams } from "react-router-dom";
import { ScoreHistoryChart, VolumeChart } from "../components/charts/Charts";
import { ErrorBox, LifecycleBadge, Loading, fmtDate, fmtNum } from "../components/common/ui";
import { useAsync } from "../hooks/useAsync";
import { saveItem } from "../services/research";
import { getTrend, getTrendHistory } from "../services/trends";

const SIGNAL_LABELS: Record<string, string> = {
  growth: "Growth",
  momentum: "Momentum",
  engagement: "Engagement",
  novelty: "Novelty",
  search_interest: "Search interest",
  cross_source_activity: "Cross-source",
};

export default function TrendDetail() {
  const { id = "" } = useParams();
  const detail = useAsync(() => getTrend(id), [id]);
  const history = useAsync(() => getTrendHistory(id), [id]);
  const [saved, setSaved] = useState(false);

  if (detail.loading) return <Loading />;
  if (detail.error || !detail.data) return <ErrorBox message={detail.error ?? "Trend not found"} />;
  const t = detail.data;
  const cov = t.coverage ?? {};
  const latestVolumes = t.weekly_volumes?.length ? t.weekly_volumes : history.data?.length ? history.data[history.data.length - 1].volumes : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{t.topic_name}</h1>
          <div className="mt-1 flex items-center gap-2 text-sm text-slate-500">
            <LifecycleBadge value={t.lifecycle} /> Updated {fmtDate(t.last_updated)}
          </div>
        </div>
        <button className="btn btn-ghost" disabled={saved} onClick={() => saveItem("trend", t.topic_id, t.topic_name).then(() => setSaved(true))}>
          {saved ? "Saved ✓" : "Save"}
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="card">
          <div className="text-xs uppercase text-slate-500">Trend Score</div>
          <div className="text-4xl font-bold">{t.trend_score === null ? "n/a" : fmtNum(t.trend_score)}</div>
          {t.trend_score === null && <p className="mt-1 text-xs text-amber-700">Withheld: signal coverage below the minimum.</p>}
        </div>
        <div className="card md:col-span-2">
          <div className="mb-2 text-sm font-semibold">Component breakdown (0–100)</div>
          <div className="space-y-2">
            {Object.entries(SIGNAL_LABELS).map(([k, label]) => {
              const v = t.signals[k];
              return (
                <div key={k} className="text-sm">
                  <div className="flex justify-between">
                    <span>{label}</span>
                    <span className={v === null ? "text-slate-400" : ""}>{v === null ? "no data" : fmtNum(v)}</span>
                  </div>
                  <div className="h-2 rounded bg-slate-100">
                    {v !== null && <div className="h-2 rounded bg-brand-500" style={{ width: `${v}%` }} />}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Coverage: {cov.sources_observed ?? 0} of {cov.sources_available ?? 0} sources observed
            {cov.signal_weight_coverage !== undefined && ` · ${(cov.signal_weight_coverage * 100).toFixed(0)}% of score weight had data`}.
            Missing signals are excluded, not counted as zero.
          </p>
        </div>
      </div>

      <div className="card">
        <h3 className="mb-2 font-semibold">Why this score</h3>
        <p className="text-sm text-slate-700">{t.explanation?.summary ?? "No explanation available."}</p>
        {t.previous_score !== null && t.trend_score !== null && (
          <p className="mt-1 text-xs text-slate-500">Previous computation: {fmtNum(t.previous_score)}</p>
        )}
        {t.explanation?.contributions && (
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-slate-500">
                <th className="py-1">Signal</th>
                <th>Value</th>
                <th>Weight</th>
                <th className="text-right">Points</th>
              </tr>
            </thead>
            <tbody>
              {t.explanation.contributions.map((c) => (
                <tr key={c.signal} className="border-t border-stone-100">
                  <td className="py-1.5">{c.label}</td>
                  <td>{c.value === null ? "no data" : fmtNum(c.value)}</td>
                  <td>{c.weight}</td>
                  <td className="text-right">{c.points === null ? "—" : fmtNum(c.points, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {(t.explanation?.missing ?? []).length > 0 && (
          <ul className="mt-3 space-y-0.5 text-xs text-slate-500">
            {t.explanation.missing!.map((m) => (
              <li key={m.signal}>
                <span className="font-medium">{m.label}:</span> {m.reason}
              </li>
            ))}
          </ul>
        )}
        {Object.keys(t.source_distribution ?? {}).length > 0 && (
          <p className="mt-3 text-xs text-slate-500">
            Documents by source: {Object.entries(t.source_distribution).map(([k, v]) => `${k} ${v}`).join(", ")}
          </p>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card">
          <VolumeChart values={latestVolumes} />
        </div>
        <div className="card">
          <ScoreHistoryChart
            points={(history.data ?? []).map((h) => ({ label: new Date(h.created_at).toLocaleDateString(), score: h.trend_score }))}
          />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card">
          <h3 className="mb-2 font-semibold">Key terms & related topics</h3>
          <div className="mb-3 flex flex-wrap gap-2">
            {t.terms.map((x) => (
              <span key={x} className="rounded bg-brand-50 px-2 py-0.5 text-sm text-brand-700">
                {x}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {t.related_topics.length === 0 && <span className="text-sm text-slate-400">No related topics yet.</span>}
            {t.related_topics.map((x) => (
              <span key={x} className="rounded-full bg-slate-100 px-3 py-1 text-sm">
                {x}
              </span>
            ))}
          </div>
        </div>
        <div className="card">
          <h3 className="mb-2 font-semibold">Representative records</h3>
          <ul className="space-y-2 text-sm">
            {t.representative_documents.map((d) => (
              <li key={d.id}>
                {d.url ? (
                  <a className="font-medium text-brand-700 hover:underline" href={d.url} target="_blank" rel="noreferrer">
                    {d.title}
                  </a>
                ) : (
                  d.title
                )}
                <div className="text-xs text-slate-500">
                  {d.source} · {fmtDate(d.published_at)}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
