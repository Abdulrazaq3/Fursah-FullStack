from __future__ import annotations

import json
import sys
import threading
from collections import defaultdict
from pathlib import Path

from ..schemas import TraceEvent


class Tracer:
    def __init__(self, jsonl_path: str = "") -> None:
        self._sequences: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._jsonl_path = Path(jsonl_path) if jsonl_path else None

    def emit(
        self,
        *,
        request_id: str,
        step: str,
        component: str,
        outcome: str,
        elapsed_ms: float = 0,
        evidence_ids: list[str] | None = None,
    ) -> TraceEvent:
        with self._lock:
            self._sequences[request_id] += 1
            sequence = self._sequences[request_id]

        event = TraceEvent(
            request_id=request_id,
            sequence=sequence,
            step=step,
            component=component,
            outcome=outcome,
            elapsed_ms=max(0, elapsed_ms),
            evidence_ids=evidence_ids or [],
        )

        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        print(line, file=sys.stdout, flush=True)

        if self._jsonl_path is not None:
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self._jsonl_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        if step in ("request_failed", "response_ready"):
            with self._lock:
                self._sequences.pop(request_id, None)
        return event
