import { NavLink } from "react-router-dom";

const TABS = [
  { to: "/monitor", label: "Overview", end: true },
  { to: "/monitor/watchlist", label: "Watchlist", end: false },
  { to: "/monitor/activity", label: "Activity", end: false },
  { to: "/monitor/notifications", label: "Notifications", end: false },
  { to: "/monitor/settings", label: "Settings", end: false },
];
export default function MonitorNav() {
  return (
    <nav className="flex gap-1 overflow-x-auto whitespace-nowrap border-b border-stone-200" aria-label="Monitor">
      {TABS.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => `px-3 py-2 text-sm ${isActive ? "border-b-2 border-brand-600 font-medium" : "text-slate-500 hover:text-slate-900"}`}>
          {t.label}
        </NavLink>
      ))}
    </nav>
  );
}
