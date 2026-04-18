from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Task2Session:
    history: list[dict[str, object]] = field(default_factory=list)
    pending_context: dict[str, object] | None = None
    last_context: dict[str, object] | None = None
    pending_slots: list[str] = field(default_factory=list)
    last_plan: dict[str, object] | None = None
    last_images: list[str] = field(default_factory=list)
    turn_count: int = 0

    def reset(self) -> None:
        self.history.clear()
        self.pending_context = None
        self.last_context = None
        self.pending_slots.clear()
        self.last_plan = None
        self.last_images.clear()
        self.turn_count = 0

    def record_turn(
        self,
        question: str,
        answer: dict[str, object],
        *,
        sql: str | None = None,
    ) -> None:
        self.turn_count += 1
        self.history.append({"Q": question, "A": answer, "sql": sql})

    def clear_pending(self) -> None:
        self.pending_context = None
        self.pending_slots.clear()
