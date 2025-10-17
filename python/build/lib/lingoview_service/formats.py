from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

from .pipeline import SubtitleResult, SubtitleSegment


def _format_timestamp(value: float) -> str:
    if value < 0:
        value = 0.0
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = int(value % 60)
    milliseconds = int(round((value - math.floor(value)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


import math


def build_srt(segments: Iterable[SubtitleSegment]) -> str:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        start = _format_timestamp(segment.start)
        end = _format_timestamp(segment.end)
        text = segment.text.strip() or "…"
        lines.extend([str(index), f"{start} --> {end}", text, ""])
    return "\n".join(lines).strip() + "\n"


def build_json(result: SubtitleResult, use_translation: bool = False) -> str:
    payload = {
        "language": result.translation_language if use_translation else result.language,
        "segments": [],
    }
    source_segments = result.translated_segments if use_translation else result.segments
    for segment in source_segments or []:
        payload["segments"].append(
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "tokens": [
                    {
                        "surface": token.surface,
                        "reading": token.reading,
                        "romaji": token.romaji,
                    }
                    for token in (segment.tokens or [])
                ]
                if segment.tokens
                else None,
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
