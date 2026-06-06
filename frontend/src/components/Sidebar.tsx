import { BarChart2, Layers, Zap } from "lucide-react";
import type { Company, IndexStats, RoundType } from "../types";

const COMPANIES: { value: Company; label: string; color: string; dot: string }[] = [
  { value: "BCG", label: "BCG X", color: "text-bcg", dot: "bg-bcg" },
  { value: "McKinsey", label: "McKinsey QB", color: "text-mckinsey-light", dot: "bg-mckinsey-light" },
];

const ROUNDS: { value: RoundType; label: string }[] = [
  { value: "All", label: "All Rounds" },
  { value: "General", label: "General" },
  { value: "OA", label: "Online Assessment" },
  { value: "Technical", label: "Technical" },
  { value: "LiveCoding", label: "Live Coding" },
  { value: "Case", label: "Case Interview" },
  { value: "PEI", label: "PEI / Behavioral" },
  { value: "TakeHome", label: "Take-Home" },
];

interface Props {
  company: Company;
  roundType: RoundType;
  onCompany: (c: Company) => void;
  onRound: (r: RoundType) => void;
  stats: IndexStats | null;
}

export function Sidebar({ company, roundType, onCompany, onRound, stats }: Props) {
  return (
    <aside className="w-64 shrink-0 flex flex-col gap-6 py-6 px-4 border-r border-zinc-800 bg-zinc-950 overflow-y-auto">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-1">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-bcg to-mckinsey-light flex items-center justify-center">
          <Zap size={16} className="text-white" />
        </div>
        <div>
          <p className="text-sm font-semibold text-zinc-100 leading-none">DS Coach</p>
          <p className="text-[11px] text-zinc-500 mt-0.5">Interview RAG</p>
        </div>
      </div>

      {/* Company filter */}
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500 px-1 mb-2">
          Company
        </p>
        <div className="flex flex-col gap-0.5">
          {COMPANIES.map((c) => (
            <button
              key={c.value}
              onClick={() => onCompany(c.value)}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${
                company === c.value
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
              }`}
            >
              <span className={`w-2 h-2 rounded-full shrink-0 ${c.dot}`} />
              {c.label}
            </button>
          ))}
        </div>
      </div>

      {/* Round filter */}
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500 px-1 mb-2">
          Round
        </p>
        <div className="flex flex-col gap-0.5">
          {ROUNDS.map((r) => (
            <button
              key={r.value}
              onClick={() => onRound(r.value)}
              className={`flex items-center px-3 py-2 rounded-md text-sm transition-colors text-left ${
                roundType === r.value
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Index stats */}
      {stats && (
        <div className="mt-auto">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500 px-1 mb-2 flex items-center gap-1.5">
            <BarChart2 size={11} /> Index
          </p>
          <div className="bg-zinc-900 rounded-lg p-3 space-y-2">
            <StatRow label="Chunks" value={stats.total_chunks} />
            {Object.entries(stats.by_source).map(([k, v]) => (
              <StatRow key={k} label={k} value={v} />
            ))}
          </div>
          <div className="bg-zinc-900 rounded-lg p-3 mt-2 space-y-2">
            <p className="text-[11px] text-zinc-500 flex items-center gap-1">
              <Layers size={11} /> By company
            </p>
            {Object.entries(stats.by_company).map(([k, v]) => (
              <StatRow key={k} label={k} value={v} />
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-zinc-500 capitalize">{label}</span>
      <span className="text-xs font-mono text-zinc-300">{value.toLocaleString()}</span>
    </div>
  );
}
