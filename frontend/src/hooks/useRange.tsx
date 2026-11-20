import { createContext, useContext, useState } from "react";

export const TIME_RANGES = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
];

const Ctx = createContext<{ range: string; setRange: (r: string) => void }>({ range: "7d", setRange: () => {} });

export function RangeProvider({ children }: { children: React.ReactNode }) {
  const [range, setRange] = useState("7d");
  return <Ctx.Provider value={{ range, setRange }}>{children}</Ctx.Provider>;
}

export const useRange = () => useContext(Ctx);
