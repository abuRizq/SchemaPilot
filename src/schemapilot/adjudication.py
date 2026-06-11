"""The human adjudication queue (FILE_2, axiom A7).

Human attention is a routed resource: the queue is ranked by
uncertainty × impact, and every answer writes back into the CCO or domain
dictionaries — the system never asks the same question twice.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class AdjudicationItem:
    item_id: str
    kind: str  # "mapping" | "match" | "fusion"
    question: str
    uncertainty: float  # 0..1 (1 = coin flip)
    impact: float  # 0..1 (row volume / column importance / stakes)
    context: dict = field(default_factory=dict)
    answer: str | None = None

    @property
    def priority(self) -> float:
        return self.uncertainty * self.impact


class AdjudicationQueue:
    def __init__(self) -> None:
        self._items: dict[str, AdjudicationItem] = {}

    def submit(self, item: AdjudicationItem) -> None:
        self._items.setdefault(item.item_id, item)

    def ranked(self) -> list[AdjudicationItem]:
        return sorted(
            (i for i in self._items.values() if i.answer is None),
            key=lambda i: (-i.priority, i.item_id),
        )

    def answer(self, item_id: str, answer: str) -> AdjudicationItem:
        item = self._items[item_id]
        item.answer = answer
        return item

    @property
    def open_count(self) -> int:
        return sum(1 for i in self._items.values() if i.answer is None)

    def save(self, path: Path | str) -> None:
        Path(path).write_text(json.dumps(
            [asdict(i) for i in sorted(self._items.values(), key=lambda i: i.item_id)],
            indent=2, ensure_ascii=False, sort_keys=True,
        ))

    @classmethod
    def load(cls, path: Path | str) -> "AdjudicationQueue":
        queue = cls()
        for raw in json.loads(Path(path).read_text()):
            queue.submit(AdjudicationItem(**raw))
        return queue
