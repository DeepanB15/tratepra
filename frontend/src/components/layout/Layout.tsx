import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { useAsync } from "../../hooks/useAsync";
import { getDiscoveryOverview } from "../../services/trends";
import { unreadCount } from "../../services/monitoring";
import Icon from "../common/Icon";
import { fmtAge } from "../common/ui";

const PRIMARY = [
  { to: "/", label: "Discover", end: true },
  { to: "/research", label: "Investigate", end: false },
  { to: "/monitor", label: "Monitor", end: false },
];
const SECONDARY = [
  { to: "/trends", label: "All trends" },
  { to: "/runs", label: "Analysis runs" },
  { to: "/sources", label: "Sources" },
  { to: "/saved", label: "Saved" },
  { to: "/history", label: "History" },
  { to: "/settings", label: "Settings" },
];

const primaryClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-3 text-sm font-medium border-b-2 ${isActive ? "border-brand-600 text-slate-900" : "border-transparent text-slate-500 hover:text-slate-900"}`;
const secondaryClass = ({ isActive }: { isActive: boolean }) => `px-2 py-1 text-xs ${isActive ? "text-slate-900 font-medium" : "text-slate-500 hover:text-slate-900"}`;

/** In-app notification bell with the unread count; refreshes on a slow poll and when the notifications page changes something. */
function NotificationBell() {
  const [n, setN] = useState<number | null>(null);
  useEffect(() => {
    const load = () => unreadCount().then((r) => setN(r.unread)).catch(() => setN(null));
    load();
    const t = setInterval(load, 60000);
    window.addEventListener("notifications-changed", load);
    return () => { clearInterval(t); window.removeEventListener("notifications-changed", load); };
  }, []);
  return (
    <NavLink to="/monitor/notifications" className="relative text-xs text-slate-600 hover:text-slate-900" aria-label={`Notifications${n ? `, ${n} unread` : ""}`}>
      Alerts{n ? <span className="ml-1 rounded-full bg-brand-600 px-1.5 py-0.5 text-[10px] font-medium text-white" data-testid="unread-badge">{n > 99 ? "99+" : n}</span> : null}
    </NavLink>
  );
}

/** Data freshness: age of the latest COMPLETED analysis run (a failed run never changes it). */
function FreshnessIndicator() {
  const { data, error } = useAsync(getDiscoveryOverview);
  if (error) return <span className="text-xs text-slate-400" title={error}>freshness unavailable</span>;
  if (!data) return <span className="text-xs text-slate-400">…</span>;
  const f = data.data_freshness;
  const tone = f.latest_successful_analysis_at === null ? "bg-slate-300" : f.overdue ? "bg-amber-500" : "bg-emerald-500";
  const failed = data.latest_run_status === "failed";
  return (
    <span
      className="flex items-center gap-1.5 text-xs text-slate-600"
      title={
        f.latest_successful_analysis_at === null
          ? "No completed analysis yet"
          : `Latest completed analysis ${new Date(f.latest_successful_analysis_at).toLocaleString()}${f.overdue ? ` — older than ${f.overdue_after_days} days` : ""}${failed ? ". The most recent run failed; shown data is from the last completed run." : ""}`
      }
    >
      <span className={`h-2 w-2 rounded-full ${tone}`} aria-hidden />
      Analysis {fmtAge(f.latest_successful_analysis_at)}
      {failed && <span className="text-rose-700">· latest run failed</span>}
    </span>
  );
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-10 border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 md:px-6">
          <NavLink to="/" className="py-3 text-base font-semibold tracking-tight">
            Tratepra
          </NavLink>
          <nav className="hidden items-center md:flex" aria-label="Primary">
            {PRIMARY.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={primaryClass}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-4">
            <NotificationBell />
            <FreshnessIndicator />
            <button className="md:hidden" onClick={() => setOpen((o) => !o)} aria-label="Toggle navigation" aria-expanded={open}>
              <Icon name="menu" />
            </button>
          </div>
        </div>
        <div className={`${open ? "block" : "hidden"} border-t border-stone-100 md:block`} onClick={() => setOpen(false)}>
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-1 px-3 py-1 md:px-5">
            <span className="flex md:hidden">
              {PRIMARY.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.end} className={secondaryClass}>
                  {n.label}
                </NavLink>
              ))}
            </span>
            {SECONDARY.map((n) => (
              <NavLink key={n.to} to={n.to} className={secondaryClass}>
                {n.label}
              </NavLink>
            ))}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 md:px-6">{children}</main>
    </div>
  );
}
