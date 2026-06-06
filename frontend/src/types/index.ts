export type Company = "Both" | "BCG" | "McKinsey";
export type RoundType = "All" | "General" | "OA" | "Technical" | "LiveCoding" | "Case" | "PEI" | "TakeHome";

export interface Source {
  source_name: string;
  source_type: string;
  company: string;
  round_type: string;
  url: string;
  score: number;
  excerpt: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  isStreaming?: boolean;
  company?: Company;
  roundType?: RoundType;
}

export interface IndexStats {
  total_chunks: number;
  by_company: Record<string, number>;
  by_source: Record<string, number>;
  by_round: Record<string, number>;
}
