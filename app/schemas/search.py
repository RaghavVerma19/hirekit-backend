from typing import List, Optional
import uuid
from pydantic import BaseModel


class SearchResultItem(BaseModel):
    id: uuid.UUID
    type: str  # "job" | "post"
    title: str
    subtitle: str
    snippet: str
    match_score: int
    url: str


class SearchResponse(BaseModel):
    query: str
    total_count: int
    results: List[SearchResultItem] = []
