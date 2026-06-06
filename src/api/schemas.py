from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    company: str = "Both"        # "BCG" | "McKinsey" | "Both"
    round_type: str = "All"      # "General" | "OA" | "Technical" | "LiveCoding" | "Case" | "PEI" | "TakeHome" | "All"
    use_hyde: bool = True
    use_multi_query: bool = True


class HealthResponse(BaseModel):
    status: str
    index_ready: bool


class IndexStats(BaseModel):
    total_chunks: int
    by_company: dict[str, int]
    by_source: dict[str, int]
    by_round: dict[str, int]
