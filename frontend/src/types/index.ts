export type Company = "Both" | "BCG" | "McKinsey";
export type RoundType = "All" | "General" | "OA" | "Technical" | "LiveCoding" | "Case" | "PEI" | "TakeHome";

export interface Source {
  source_name: string;
  source_type: string;
  company: string;
  round_type: string;
  url: string;
  score: number;
  trust_score: number;
  conflict: boolean;
  conflict_type: string;
  conflict_note: string;
  excerpt: string;
}

export interface QualityResult {
  score: number;
  pass: boolean;
  dimensions: {
    coverage?: number;
    source_quality?: number;
    specificity?: number;
    actionability?: number;
  };
  gaps: string[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  quality?: QualityResult;
  isStreaming?: boolean;
  isRefining?: boolean;
  company?: Company;
  roundType?: RoundType;
}

export interface IndexStats {
  total_chunks: number;
  by_company: Record<string, number>;
  by_source: Record<string, number>;
  by_round: Record<string, number>;
}
