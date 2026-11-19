from dataclasses import dataclass, field
from typing import List

from models.chunk_models import Chunk


@dataclass
class BudgetResult:
    selected: List[Chunk]
    skipped: int
    estimated_context_tokens: int


class TokenBudgetService:
    def apply(self, chunks: List[Chunk], budget: int, max_chunks: int) -> BudgetResult:
        """Select chunks in order until adding the next would exceed the budget."""
        selected: List[Chunk] = []
        total = 0
        for chunk in chunks:
            if len(selected) >= max_chunks:
                break
            if total + chunk.estimated_tokens > budget:
                break
            selected.append(chunk)
            total += chunk.estimated_tokens
        return BudgetResult(
            selected=selected,
            skipped=len(chunks) - len(selected),
            estimated_context_tokens=total,
        )
