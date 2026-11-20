import { useState } from "react";
import { NavLink } from "react-router-dom";
import { TIME_RANGES, useRange } from "../../hooks/useRange";
import Icon from "../common/Icon";

const NAV = [
  { to: "/", label: "Home", icon: "home" },
  { to: "/research", label: "Research", icon: "search" },
  { to: "/trends", label: "Trends", icon: "chart" },
  { to: "/saved", label: "Saved", icon: "bookmark" },
  { to: "/history", label: "History", icon: "clock" },
  { to: "/sources", label: "Sources", icon: "layers" },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium transition ${
    isActive ? "bg-stone-100 text-slate-900" : "text-slate-600 hover:bg-stone-100/70"
  }`;

export default function Layout({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const { range, setRange } = useRange();

  return (
    <div className="min-h-screen md:flex">
      <aside
        className={`${open ? "flex" : "hidden"} w-full shrink-0 flex-col border-r border-stone-200/70 bg-[#f6f5f2] p-4 md:sticky md:top-0 md:flex md:h-screen md:w-64`}
      >
        <div className="mb-6 px-2 text-2xl font-semibold tracking-tight">Tratepra</div>
        <nav className="space-y-1" onClick={() => setOpen(false)}>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={linkClass}>
              <Icon name={n.icon} /> {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto" onClick={() => setOpen(false)}>
          <NavLink to="/settings" className={linkClass}>
            <Icon name="settings" /> Settings
          </NavLink>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3 px-4 py-4 md:justify-end md:px-8">
          <button className="btn btn-ghost md:hidden" onClick={() => setOpen((o) => !o)} aria-label="Toggle navigation">
            <Icon name="menu" />
          </button>
          <div className="flex items-center gap-3">
            <label className="relative flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm font-medium">
              <Icon name="calendar" size={16} />
              <select
                className="appearance-none bg-transparent pr-5 focus:outline-none"
                value={range}
                onChange={(e) => setRange(e.target.value)}
                aria-label="Time range"
              >
                {TIME_RANGES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              <Icon name="chevron" size={14} className="pointer-events-none absolute right-3" />
            </label>
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-stone-200 text-slate-600" title="Local single-user mode">
              <Icon name="user" size={18} />
            </div>
          </div>
        </div>
        <main className="px-4 pb-12 md:px-10">{children}</main>
      </div>
    </div>
  );
}
