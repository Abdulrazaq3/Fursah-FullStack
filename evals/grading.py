"""A deterministic evaluation score, shared by the current catalog graders."""
from dataclasses import dataclass


@dataclass
class Grade:
    metric: str
    score: float  # 0..1
    reason: str = ""
