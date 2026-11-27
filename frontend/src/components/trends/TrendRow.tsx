import { Link } from "react-router-dom";
import type { TrendSummary } from "../../types";
import { Sparkline } from "../charts/Charts";
import { ActivityBadge, LifecycleBadge, MomentumValue, ScoreValue, fmtAge, fmtPct } from "../common/ui";

/** One discovery result. Every value comes from the stored observation of the latest completed run. */
export default function TrendRow({ t }: { t: TrendSummary }) {
  return (
    <li className="py-3">
      <Link to={`/trends/${t.topic_id}`} className="group grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-semibold text-slate-900 group-hover:underline">{t.topic_name}</span>
            <LifecycleBadge value={t.lifecycle} />
            <ActivityBadge value={t.activity_state} />
            {t.is_new && <span className="rounded border border-sky-200 px-1.5 py-px text-[11px] font-medium text-sky-700">new</span>}
            {t.needs_review && (
              <span className="rounded border border-slate-300 px-1.5 py-px text-[11px] text-slate-500" title="Topic name or identity flagged for review">
                review
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-slate-600">{t.explanation}</p>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-slate-500">
            <span title="Growth: latest window vs the previous window">Growth {fmtPct(t.growth)}</span>
            <MomentumValue direction={t.momentum_direction} />
            <span title="Documents assigned to this topic in the latest run">{t.supporting_documents ?? "—"} docs</span>
            <span>{t.source_count} source{t.source_count === 1 ? "" : "s"}</span>
            <span title="Time of the completed run that last observed this topic">Observed {fmtAge(t.last_observed_at)}</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden w-24 sm:block">
            <Sparkline values={t.sparkline} />
          </div>
          <div className="w-16 text-right">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">Score</div>
            <ScoreValue score={t.trend_score} withheld={t.score_withheld} coverage={t.score_coverage} />
          </div>
        </div>
      </Link>
    </li>
  );
}
