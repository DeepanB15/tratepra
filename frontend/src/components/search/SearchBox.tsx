import { useEffect, useRef, useState } from "react";
import { useAsync } from "../../hooks/useAsync";
import { useRange } from "../../hooks/useRange";
import { getSources } from "../../services/research";
import Icon from "../common/Icon";

export const SUGGESTIONS = [
  { icon: "trend", text: "What are the emerging AI coding trends?" },
  { icon: "layers", text: "Latest on on-device LLMs" },
  { icon: "chart", text: "Top developer tools this week" },
  { icon: "spark", text: "Open-source model releases this month" },
];

interface Props {
  initialQuery?: string;
  loading?: boolean;
  suggestions?: boolean;
  onSubmit: (query: string, sources: string[], timeRange: string) => void;
}

export default function SearchBox({ initialQuery = "", loading, suggestions = true, onSubmit }: Props) {
  const { data: sources } = useAsync(getSources);
  const { range } = useRange();
  const [query, setQuery] = useState(initialQuery);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [menu, setMenu] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => setQuery(initialQuery), [initialQuery]);
  useEffect(() => {
    const close = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setMenu(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const isOn = (key: string, available: boolean) => (key in selected ? selected[key] : available);
  const chosen = (sources ?? []).filter((s) => isOn(s.key, s.available)).map((s) => s.key);
  const canSubmit = !loading && query.trim().length >= 3 && chosen.length > 0;
  const submit = () => canSubmit && onSubmit(query.trim(), chosen, range);

  return (
    <div className="mx-auto w-full max-w-3xl">
      <div className="rounded-3xl border border-stone-200 bg-white p-4 shadow-[0_8px_30px_rgba(0,0,0,0.04)]">
        <textarea
          rows={2}
          className="w-full resize-none bg-transparent px-2 py-1 text-base placeholder:text-slate-400 focus:outline-none"
          placeholder="Ask anything…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <div className="mt-2 flex items-center justify-between">
          <div className="relative" ref={box}>
            <button type="button" className="pill" onClick={() => setMenu((m) => !m)} aria-expanded={menu}>
              <Icon name="layers" size={16} /> Sources <span className="text-slate-400">{chosen.length}</span>
              <Icon name="chevron" size={14} />
            </button>
            {menu && (
              <div className="absolute left-0 top-12 z-10 w-72 rounded-2xl border border-stone-200 bg-white p-2 shadow-lg">
                {(sources ?? []).map((s) => {
                  const on = isOn(s.key, s.available);
                  return (
                    <label key={s.key} className="flex cursor-pointer items-start gap-3 rounded-xl p-2 hover:bg-stone-50">
                      <input
                        type="checkbox"
                        className="mt-1 accent-[#2b5755]"
                        checked={on}
                        onChange={() => setSelected((p) => ({ ...p, [s.key]: !on }))}
                      />
                      <span className="text-sm">
                        <span className="font-medium">{s.name}</span>
                        {!s.available && <span className="block text-xs text-amber-700">Not configured: {s.reason}</span>}
                      </span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            aria-label="Run research"
            className="flex h-10 w-12 items-center justify-center rounded-xl bg-brand-600 text-white transition hover:bg-brand-700 disabled:opacity-40"
          >
            {loading ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            ) : (
              <Icon name="arrow" />
            )}
          </button>
        </div>
      </div>

      {suggestions && (
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          {SUGGESTIONS.map((s) => (
            <button key={s.text} type="button" className="pill" onClick={() => setQuery(s.text)}>
              <Icon name={s.icon} size={16} /> {s.text}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
