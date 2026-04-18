from __future__ import annotations

from typing import cast


def format_answer(
    content: str, chart_artifact: dict[str, object] | None = None
) -> dict[str, object]:
    images: list[str] = []
    if chart_artifact and isinstance(chart_artifact.get("image"), list):
        raw_images = cast(list[object], chart_artifact.get("image") or [])
        images = [str(item) for item in raw_images]
    return {
        "content": content,
        "image": images,
    }
