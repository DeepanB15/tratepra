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
