from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment, TranscriptionInfo

from .config import ServiceSettings
from .vad import AudioChunk, chunk_audio


@dataclass
class WhisperSegmentResult:
    start: float
    end: float
    text: str
    language: str


class WhisperClient:
    """Wrapper around local faster-whisper inference with chunked audio."""

    def __init__(self, settings: ServiceSettings) -> None:
        self.settings = settings
        self._model = _load_model(
            settings.whisper_model,
            settings.whisper_device,
            settings.whisper_compute_type,
        )
        self._apply_boundary_filter = True
        self._temperature = self._normalize_temperature(settings.whisper_temperature)

    async def transcribe(
        self,
        media_path: Path,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> List[WhisperSegmentResult]:
        chunks = await chunk_audio(media_path, self.settings)
        segments: List[WhisperSegmentResult] = []
        language_counter: Counter[str] = Counter()

        total_chunks = len(chunks)

        def report_progress(completed: int) -> None:
            if progress_cb:
                try:
                    progress_cb(completed, total_chunks)
                except Exception:  # pragma: no cover - defensive guard
                    pass

        for index, chunk in enumerate(chunks, start=1):
            chunk_segments = await self._transcribe_chunk(chunk)
            for segment in chunk_segments:
                segments.append(segment)
                language_counter[segment.language] += 1
            try:
                chunk.path.unlink()
            except OSError:
                pass

            report_progress(index)

        if total_chunks == 0:
            report_progress(0)

        segments.sort(key=lambda s: s.start)

        dominant_language = "und"
        if language_counter:
            dominant_language = language_counter.most_common(1)[0][0]
            for segment in segments:
                if segment.language == "und":
                    segment.language = dominant_language

        return segments

    async def _transcribe_chunk(self, chunk: AudioChunk) -> List[WhisperSegmentResult]:
        segment_objects, info = await asyncio.to_thread(
            self._run_model, chunk
        )

        language = info.language or "und"
        results: List[WhisperSegmentResult] = []

        for segment in segment_objects:
            text = segment.text.strip()
            if not text:
                continue

            absolute_start = chunk.start + segment.start
            absolute_end = chunk.start + segment.end

            # 丢弃明显在静音区域的重复片段
            if self._apply_boundary_filter:
                if absolute_end < chunk.speech_start - 0.2:
                    continue
                if absolute_start > chunk.speech_end + 0.2:
                    continue

            clamped_start = max(chunk.start, absolute_start)
            clamped_end = min(chunk.end, absolute_end)
            clamped_end = max(clamped_end, clamped_start + 0.05)

            results.append(
                WhisperSegmentResult(
                    start=clamped_start,
                    end=clamped_end,
                    text=text,
                    language=getattr(segment, "language", None) or language,
                )
            )

        return results

    def _run_model(self, chunk: AudioChunk) -> Tuple[List[Segment], TranscriptionInfo]:
        result_segments: List[Segment] = []
        generator, info = self._model.transcribe(
            str(chunk.path),
            beam_size=self.settings.whisper_beam_size,
            temperature=self._temperature,
            language=self.settings.whisper_language,
            vad_filter=True,
            without_timestamps=False,
            condition_on_previous_text=self.settings.whisper_condition_on_previous_text,
            compression_ratio_threshold=self.settings.whisper_compression_ratio_threshold,
            log_prob_threshold=self.settings.whisper_log_prob_threshold,
            no_speech_threshold=self.settings.whisper_no_speech_threshold,
        )

        for seg in generator:
            result_segments.append(seg)

        return result_segments, info

    @staticmethod
    def _normalize_temperature(value: float) -> tuple[float, ...]:
        # follow faster-whisper default temperature fallback to avoid greedy stalls
        if value <= 0:
            return (0.0, 0.2, 0.4)
        if value < 0.4:
            return (value, 0.2, 0.4)
        return (value,)


@lru_cache(maxsize=4)
def _load_model(model_name: str, device: str, compute_type: str) -> WhisperModel:
    return WhisperModel(
        model_size_or_path=model_name,
        device=device,
        compute_type=compute_type,
    )
