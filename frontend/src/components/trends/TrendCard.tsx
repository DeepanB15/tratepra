import { Link } from "react-router-dom";
import type { TrendSummary } from "../../types";
import { Sparkline } from "../charts/Charts";
import { LifecycleBadge, fmtDate, fmtNum } from "../common/ui";

export default function TrendCard({ t }: { t: TrendSummary }) {
  const cov = t.coverage ?? {};
  return (
    <Link to={`/trends/${t.topic_id}`} className="card block transition hover:border-brand-500">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold">{t.topic_name}</h3>
        <LifecycleBadge value={t.lifecycle} />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
        <div>
          <div className="text-xs text-slate-500">Trend Score</div>
          <div className="text-xl font-bold">{t.trend_score === null ? "n/a" : fmtNum(t.trend_score)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500">Growth</div>
          <div className="text-xl font-bold">{t.growth === null ? "n/a" : `${fmtNum(t.growth, 0)}%`}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500">Sources</div>
          <div className="text-xl font-bold">
            {cov.sources_observed ?? 0}/{cov.sources_available ?? 0}
          </div>
        </div>
      </div>
      {t.trend_score === null && cov.score_withheld && (
        <p className="mt-2 text-xs text-amber-700">Score withheld: not enough signal coverage.</p>
      )}
      <div className="mt-2">
        <Sparkline values={t.sparkline} />
      </div>
      <div className="text-xs text-slate-400">Updated {fmtDate(t.last_updated)}</div>
    </Link>
  );
}
