import type { ClaimStatus, EvidenceRole, QualityDimension } from "../../types";

const DIM_STYLE: Record<string, string> = {
  strong: "border-slate-700 text-slate-800",
  moderate: "border-slate-500 text-slate-700",
  limited: "border-slate-400 text-slate-600",
  insufficient: "border-slate-300 text-slate-500",
};
/** Filled segments out of 4 - a descriptive scale, deliberately not a percentage. */
const SEGMENTS: Record<string, number> = { insufficient: 1, limited: 2, moderate: 3, strong: 4 };

export function QualityCard({ name, dim }: { name: string; dim: QualityDimension }) {
  return (
    <div className="rounded border border-stone-200 p-2.5" data-testid={`quality-${name}`}>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{name.replace("_", " ")}</div>
      <div className={`mt-1 inline-block rounded border px-1.5 py-px text-xs font-medium ${DIM_STYLE[dim.label]}`}>{dim.text}</div>
      <div className="mt-1.5 flex gap-0.5" aria-hidden>
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={`h-1 w-6 rounded-sm ${i <= SEGMENTS[dim.label] ? "bg-slate-600" : "bg-stone-200"}`} />
        ))}
      </div>
      <p className="mt-1.5 text-xs text-slate-600">{dim.explanation}</p>
    </div>
  );
}

const CLAIM_LABEL: Record<ClaimStatus, string> = {
  supported: "Supported (lexical check)",
  partially_supported: "Partially supported",
  contradicted: "Contradicting evidence found",
  unverified: "Unverified",
  insufficient_evidence: "Insufficient evidence",
};
const CLAIM_STYLE: Record<ClaimStatus, string> = {
  supported: "border-emerald-300 bg-emerald-50 text-emerald-800",
  partially_supported: "border-sky-300 bg-sky-50 text-sky-800",
  contradicted: "border-rose-300 bg-rose-50 text-rose-800",
  unverified: "border-amber-300 bg-amber-50 text-amber-800",
  insufficient_evidence: "border-stone-300 bg-stone-50 text-slate-600",
};
export const claimLabel = (s: ClaimStatus) => CLAIM_LABEL[s];
export function ClaimBadge({ status }: { status: ClaimStatus }) {
  return <span className={`rounded border px-1.5 py-px text-[11px] font-medium ${CLAIM_STYLE[status]}`}>{CLAIM_LABEL[status]}</span>;
}

export function RoleBadge({ role }: { role: EvidenceRole }) {
  const s = role === "contradictory" ? "border-rose-300 text-rose-700" : role === "supporting" ? "border-emerald-300 text-emerald-700" : "border-stone-300 text-slate-500";
  return <span className={`rounded border px-1.5 py-px text-[11px] ${s}`}>{role}</span>;
}

const ART: Record<string, string> = {
  full: "Full article text",
  partial: "Partial article text",
  rss_only: "Feed summary only",
  unavailable: "Article unavailable",
  failed: "Article fetch failed",
  too_short: "Article too short",
};
export function ArticleBadge({ status }: { status: string }) {
  const full = status === "full" || status === "partial";
  return <span className={`rounded border px-1.5 py-px text-[11px] ${full ? "border-slate-400 text-slate-700" : "border-stone-300 text-slate-500"}`}>{ART[status] ?? status}</span>;
}
