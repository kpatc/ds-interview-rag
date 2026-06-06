import { ExternalLink, MessageSquare, FileText, Play, Star } from "lucide-react";
import type { Source } from "../types";

const SOURCE_META: Record<string, { icon: React.ReactNode; color: string; bg: string }> = {
  reddit: {
    icon: <MessageSquare size={12} />,
    color: "text-orange-400",
    bg: "bg-orange-400/10 border-orange-400/20",
  },
  glassdoor: {
    icon: <Star size={12} />,
    color: "text-green-400",
    bg: "bg-green-400/10 border-green-400/20",
  },
  youtube: {
    icon: <Play size={12} />,
    color: "text-red-400",
    bg: "bg-red-400/10 border-red-400/20",
  },
  article: {
    icon: <FileText size={12} />,
    color: "text-blue-400",
    bg: "bg-blue-400/10 border-blue-400/20",
  },
  forum: {
    icon: <MessageSquare size={12} />,
    color: "text-purple-400",
    bg: "bg-purple-400/10 border-purple-400/20",
  },
  teamblind: {
    icon: <MessageSquare size={12} />,
    color: "text-cyan-400",
    bg: "bg-cyan-400/10 border-cyan-400/20",
  },
};

const COMPANY_COLOR: Record<string, string> = {
  BCG: "text-bcg bg-bcg/10 border-bcg/20",
  McKinsey: "text-mckinsey-light bg-mckinsey/10 border-mckinsey/20",
  Both: "text-zinc-300 bg-zinc-700/30 border-zinc-700",
};

interface Props {
  source: Source;
  index: number;
}

export function SourceCard({ source }: Props) {
  const meta = SOURCE_META[source.source_type] ?? SOURCE_META.article;
  const companyColor = COMPANY_COLOR[source.company] ?? COMPANY_COLOR.Both;

  return (
    <div className={`rounded-lg border p-3 text-xs space-y-2 animate-fade-in ${meta.bg}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className={`shrink-0 ${meta.color}`}>{meta.icon}</span>
          <span className="font-medium text-zinc-200 truncate">
            {source.source_name || source.source_type}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={`px-1.5 py-0.5 rounded border text-[10px] font-medium ${companyColor}`}>
            {source.company}
          </span>
          {source.url && (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <ExternalLink size={11} />
            </a>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        <span className="text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded text-[10px]">
          {source.round_type}
        </span>
        <span className="text-zinc-600 text-[10px] ml-auto">
          score {source.score.toFixed(3)}
        </span>
      </div>

      <p className="text-zinc-400 leading-relaxed line-clamp-3">{source.excerpt}</p>
    </div>
  );
}
