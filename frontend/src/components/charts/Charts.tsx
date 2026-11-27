import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Bar, BarChart, CartesianGrid } from "recharts";

export function Sparkline({ values }: { values: number[] }) {
  if (!values.length) return <span className="text-xs text-slate-400">no activity data</span>;
  const data = values.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={36}>
      <LineChart data={data}>
        <Line type="monotone" dataKey="v" stroke="#2b5755" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function VolumeChart({ values, label = "Documents per window" }: { values: number[]; label?: string }) {
  const data = values.map((v, i) => ({ window: `W${i + 1}`, documents: v }));
  return (
    <div>
      <div className="mb-1 text-sm text-slate-500">{label}</div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="window" />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Bar dataKey="documents" fill="#3b6f6c" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ScoreHistoryChart({ points }: { points: { label: string; score: number | null }[] }) {
  return (
    <div>
      <div className="mb-1 text-sm text-slate-500">Trend Score per scoring run</div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={points}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" />
          <YAxis domain={[0, 100]} />
          <Tooltip />
          <Line type="monotone" dataKey="score" stroke="#2b5755" strokeWidth={2} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Points contributed by each signal to the final score (only signals that had data). */
export function ContributionChart({ rows }: { rows: { label: string; points: number | null; weight: number }[] }) {
  const data = rows.filter((r) => r.points !== null).map((r) => ({ label: r.label, points: Number((r.points as number).toFixed(2)) }));
  if (!data.length) return <p className="text-xs text-slate-500">No signal contributed to a score.</p>;
  return (
    <ResponsiveContainer width="100%" height={Math.max(120, data.length * 34)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="label" width={110} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v: number) => [`${v} points`, "Contribution"]} />
        <Bar dataKey="points" fill="#3b6f6c" radius={[0, 3, 3, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Observed document volume per analysis run (real stored observations, oldest first). */
export function HistoryVolumeChart({ points }: { points: { label: string; volume: number; legacy: boolean }[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={points}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v: number, _n, p) => [`${v} documents${(p.payload as { legacy: boolean }).legacy ? " (legacy observation, no run id)" : ""}`, "Volume"]} />
        <Bar dataKey="volume" fill="#3b6f6c" radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
