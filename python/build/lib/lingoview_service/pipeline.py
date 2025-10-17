from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional
import re

from rich.console import Console

from .config import ServiceSettings, load_settings
from .audio_processing import VocalSeparationError, separate_vocals
from .mecab_correction import MeCabTextCorrector
from .tokenizer import LingoViewTokenizer, TokenDetail, get_tokenizer
from .transcribe import WhisperClient, WhisperSegmentResult
from .openai_transcribe import OpenAIWhisperClient
from .translate import TranslatorClient, TranslationContext

console = Console()


@dataclass
class SubtitleSegment:
    start: float
    end: float
    text: str
    tokens: Optional[List[TokenDetail]] = None


@dataclass
class SubtitleResult:
    segments: List[SubtitleSegment]
    language: str
    translated_segments: Optional[List[SubtitleSegment]] = None
    translation_language: Optional[str] = None


@dataclass
class PipelineProgress:
    stage: str
    completed: int
    total: Optional[int] = None
    message: Optional[str] = None


class SubtitlePipeline:
    """Coordinates transcription, translation, tokenization and caching."""

    def __init__(
        self,
        settings: Optional[ServiceSettings] = None,
        whisper_client: Optional[WhisperClient] = None,
        translator_client: Optional[TranslatorClient] = None,
        tokenizer: Optional[LingoViewTokenizer] = None,
    ) -> None:
        self.settings = settings or load_settings()
        backend = (self.settings.whisper_backend or "local").lower()
        if backend == "openai":
            self.whisper = whisper_client or OpenAIWhisperClient(self.settings)  # type: ignore[assignment]
        else:
            self.whisper = whisper_client or WhisperClient(self.settings)
        self.translator = translator_client or TranslatorClient(self.settings)
        self.tokenizer: LingoViewTokenizer = tokenizer or get_tokenizer(self.settings)
        self.corrector = MeCabTextCorrector(self.settings)

    async def generate(
        self,
        media_path: Path,
        target_language: Optional[str] = None,
        *,
        media_title: Optional[str] = None,
        progress_callback: Optional[Callable[[PipelineProgress], None]] = None,
    ) -> SubtitleResult:
        media_path = media_path.expanduser().resolve()
        resolved_title = media_title or media_path.stem

        processed_media_path = media_path
        if self.settings.enable_vocal_separation:
            try:
                processed_media_path = separate_vocals(media_path, self.settings)
                console.log(
                    f"[cyan]Using vocals-only audio for transcription: {processed_media_path}"
                )
            except VocalSeparationError as error:
                console.log(
                    f"[yellow]Vocal separation failed: {error}. Falling back to original audio.[/yellow]"
                )
                processed_media_path = media_path

        def report(progress: PipelineProgress) -> None:
            if progress_callback:
                try:
                    progress_callback(progress)
                except Exception:  # pragma: no cover - defensive
                    pass
            total_text = f"/{progress.total}" if progress.total else ""
            message = progress.message or f"{progress.stage}: {progress.completed}{total_text}"
            console.log(f"[cyan]{message}[/cyan]")

        console.log(f"[cyan]Transcribing[/cyan] {media_path}")
        report(PipelineProgress(stage="transcribe", completed=0, message="开始音频切分与转写…"))
        transcribe_state = {"completed": 0, "total": 0}

        def handle_transcribe_progress(completed: int, total: int) -> None:
            transcribe_state["completed"] = completed
            transcribe_state["total"] = total
            report(
                PipelineProgress(
                    stage="transcribe",
                    completed=completed,
                    total=total,
                    message=(
                        f"转写进度：{completed}/{total}" if total else "转写进行中…"
                    ),
                )
            )

        whisper_segments: List[WhisperSegmentResult] = await self.whisper.transcribe(
            processed_media_path,
            progress_cb=handle_transcribe_progress,
        )
        report(
            PipelineProgress(
                stage="transcribe",
                completed=transcribe_state["completed"],
                total=transcribe_state["total"] or None,
                message=(
                    f"转写完成，处理 {transcribe_state['completed']} 个音频分片，生成 {len(whisper_segments)} 个原始段落"
                    if transcribe_state["completed"]
                    else f"转写完成，共检测到 {len(whisper_segments)} 个原始段落"
                ),
            )
        )

        should_use_mecab = self.corrector.enabled and self._should_apply_mecab(whisper_segments)
        if should_use_mecab:
            whisper_segments, mecab_summary = self.corrector.correct_segments(whisper_segments)
            if mecab_summary and mecab_summary.corrected_segments:
                report(
                    PipelineProgress(
                        stage="mecab",
                        completed=mecab_summary.corrected_segments,
                        total=mecab_summary.total_segments,
                        message=(
                            f"MeCab 校正完成，对 {mecab_summary.corrected_segments}/"
                            f"{mecab_summary.total_segments} 个片段进行了调整"
                        ),
                    )
                )
            elif mecab_summary:
                report(
                    PipelineProgress(
                        stage="mecab",
                        completed=0,
                        total=mecab_summary.total_segments,
                        message="MeCab 校正未发现需要调整的片段",
                    )
                )
        elif self.corrector.enabled:
            report(
                PipelineProgress(
                    stage="mecab",
                    completed=0,
                    message="检测到当前字幕以非日语为主，跳过 MeCab 校正",
                )
            )

        whisper_segments = self._merge_language_specific_segments(whisper_segments)
        whisper_segments = self._normalise_segment_languages(whisper_segments)
        whisper_segments = self._filter_duplicate_whisper_segments(whisper_segments)
        primary_language = self._determine_primary_language(whisper_segments)
        whisper_segments = [
            WhisperSegmentResult(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                language=primary_language,
            )
            for seg in whisper_segments
        ]

        segments: List[SubtitleSegment] = []
        for seg in whisper_segments:
            text = seg.text.strip()
            if not text:
                continue
            tokens = self.tokenizer.tokenize(text, primary_language)
            segments.append(
                SubtitleSegment(start=seg.start, end=seg.end, text=text, tokens=tokens)
            )

        translated_segments: Optional[List[SubtitleSegment]] = None
        dominant_language = primary_language
        if target_language and segments:
            self.translator.begin_usage_session()
            console.log(f"[cyan]Translating to {target_language}[/cyan]")
            report(
                PipelineProgress(
                    stage="translate",
                    completed=0,
                    total=len(segments),
                    message=f"准备翻译 {len(segments)} 条字幕…",
                )
            )
            usage_summary: dict[str, dict[str, int]] = {}
            try:
                translated_segments = await self._translate_segments(
                    segments,
                    target_language,
                    dominant_language,
                    resolved_title,
                    progress_callback=lambda completed, total: report(
                        PipelineProgress(
                            stage="translate",
                            completed=completed,
                            total=total,
                            message=f"翻译进度：{completed}/{total}",
                        )
                    ),
                )
            finally:
                usage_snapshot = self.translator.end_usage_session()
                if usage_snapshot:
                    usage_summary = usage_snapshot
                    console.log(
                        f"[cyan]Translation token usage: {self._format_usage_summary(usage_summary)}[/cyan]"
                    )
            report(
                PipelineProgress(
                    stage="translate",
                    completed=len(segments),
                    total=len(segments),
                    message=self._build_translation_summary(len(segments), usage_summary),
                )
            )
        elif target_language:
            console.log("[yellow]未检测到字幕片段，跳过翻译。[/yellow]")
            report(
                PipelineProgress(
                    stage="translate",
                    completed=0,
                    message="未检测到字幕片段，跳过翻译。",
                )
            )

        segments, translated_segments = self._sort_segments_with_translations(
            segments,
            translated_segments,
        )
        segments, translated_segments = self._deduplicate_segments(
            segments,
            translated_segments,
        )

        return SubtitleResult(
            segments=segments,
            language=dominant_language,
            translated_segments=translated_segments,
            translation_language=target_language if translated_segments else None,
        )

    async def _translate_segments(
        self,
        segments: List[SubtitleSegment],
        target_language: str,
        source_language: str,
        media_title: Optional[str],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[SubtitleSegment]:
        results: List[SubtitleSegment] = []
        total_segments = len(segments)
        for index, segment in enumerate(segments):
            context = TranslationContext(
                title=media_title,
                previous_text=segments[index - 1].text if index > 0 else None,
                next_text=segments[index + 1].text if index + 1 < total_segments else None,
                segment_index=index,
                total_segments=total_segments,
            )
            translated = await self.translator.translate_text(
                segment.text,
                target_language=target_language,
                source_language=source_language,
                context=context,
            )
            translated = translated.strip()
            tokens = self.tokenizer.tokenize(translated or segment.text, target_language)
            results.append(
                SubtitleSegment(
                    start=segment.start,
                    end=segment.end,
                    text=translated or segment.text,
                    tokens=tokens,
                )
            )
            if progress_callback:
                try:
                    progress_callback(index + 1, total_segments)
                except Exception:  # pragma: no cover - defensive
                    pass
        return results

    def run_sync(
        self,
        media_path: Path,
        target_language: Optional[str] = None,
        *,
        media_title: Optional[str] = None,
        progress_callback: Optional[Callable[[PipelineProgress], None]] = None,
    ) -> SubtitleResult:
        return asyncio.run(
            self.generate(
                media_path,
                target_language,
                media_title=media_title,
                progress_callback=progress_callback,
            )
        )

    _abbreviation_pattern = re.compile(r"\b(?:[A-Z]\.){2,}")
    _sentence_pattern = re.compile(r"[。．！？!?…]+|\.(?!\w)")

    def _merge_language_specific_segments(
        self, segments: List[WhisperSegmentResult]
    ) -> List[WhisperSegmentResult]:
        if not segments:
            return []

        merged: List[WhisperSegmentResult] = []
        buffer_text: List[str] = []
        buffer_start: float | None = None
        buffer_end: float | None = None
        buffer_lang: Optional[str] = None

        def flush_buffer() -> None:
            nonlocal buffer_text, buffer_start, buffer_end, buffer_lang
            if buffer_text and buffer_start is not None and buffer_end is not None:
                merged.append(
                    WhisperSegmentResult(
                        start=buffer_start,
                        end=buffer_end,
                        text=" ".join(buffer_text),
                        language=buffer_lang or "en",
                    )
                )
            buffer_text = []
            buffer_start = None
            buffer_end = None
            buffer_lang = None

        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            lang = (seg.language or "und").lower()
            is_english = lang.startswith("en") or (
                lang.startswith("und") and bool(re.search(r"[A-Za-z]", text))
            )

            if is_english:
                if not buffer_text:
                    buffer_start = seg.start
                    buffer_lang = seg.language or "en"
                buffer_text.append(text)
                buffer_end = seg.end

                if self._english_sentence_complete(text):
                    flush_buffer()
                continue

            # non-english; ensure buffer flushed first
            flush_buffer()
            merged.append(seg)

        flush_buffer()
        return merged

    _english_terminal_re = re.compile(r"[\.!?…]+(?:[\"'”’\)\]]+)?\s*\Z")
    _overlap_cleanup_re = re.compile(r"[\s\u3000、。，．！？!?,．…・\-]+")

    def _english_sentence_complete(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if self._english_terminal_re.search(stripped):
            return True
        return False

    def _split_segment(self, segment: WhisperSegmentResult) -> List[tuple[float, float, str]]:
        text = segment.text.strip()
        if not text:
            return [(segment.start, segment.end, text)]

        language = (segment.language or "und").lower()
        # English（以及 Whisper 输出为 UND 但包含空格的句子）维持原样，避免句子被截断导致翻译缺词。
        if language.startswith("en"):
            return [(segment.start, segment.end, text)]

        placeholders: dict[str, str] = {}

        def mask(match: re.Match[str]) -> str:
            key = f"__ABBR{len(placeholders)}__"
            placeholders[key] = match.group(0)
            return key

        masked = self._abbreviation_pattern.sub(mask, text)

        sentences: List[str] = []
        last = 0
        for match in self._sentence_pattern.finditer(masked):
            end = match.end()
            sentence = masked[last:end].strip()
            if sentence:
                sentences.append(sentence)
            last = end
        remainder = masked[last:].strip()
        if remainder:
            sentences.append(remainder)

        if not sentences:
            sentences = [masked]

        def restore(value: str) -> str:
            for key, original in placeholders.items():
                value = value.replace(key, original)
            return value.strip()

        sentences = [restore(sentence) for sentence in sentences if restore(sentence)]

        if len(sentences) <= 1:
            return [(segment.start, segment.end, text)]

        total_chars = sum(len(sentence) for sentence in sentences)
        duration = max(0.01, segment.end - segment.start)
        current_start = segment.start
        parts: List[tuple[float, float, str]] = []

        for index, sentence in enumerate(sentences):
            weight = (len(sentence) / total_chars) if total_chars else (1 / len(sentences))
            part_duration = weight * duration
            part_end = segment.end if index == len(sentences) - 1 else min(segment.end, current_start + part_duration)
            parts.append((current_start, part_end, sentence))
            current_start = part_end

        return parts

    _japanese_char_re = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
    _latin_char_re = re.compile(r"[A-Za-z]")

    def _normalise_segment_languages(
        self, segments: List[WhisperSegmentResult]
    ) -> List[WhisperSegmentResult]:
        if not segments:
            return []

        normalised: List[WhisperSegmentResult] = []
        for seg in segments:
            language = self._resolve_language(seg.text, seg.language)
            normalised.append(
                WhisperSegmentResult(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text,
                    language=language,
                )
            )
        return normalised

    def _resolve_language(self, text: str, detected: Optional[str]) -> str:
        value = (detected or '').lower()
        if 'ja' in value:
            return 'ja'
        if 'en' in value:
            return 'en'

        if self._japanese_char_re.search(text):
            return 'ja'
        if self._latin_char_re.search(text):
            return 'en'

        # fallback: prefer Japanese for other CJK scripts, otherwise English
        return 'ja'

    def _determine_primary_language(
        self, segments: List[WhisperSegmentResult]
    ) -> str:
        for seg in segments:
            if seg.language in {"ja", "en"}:
                return seg.language
        return "ja"

    def _sort_segments_with_translations(
        self,
        segments: List[SubtitleSegment],
        translated: Optional[List[SubtitleSegment]],
    ) -> tuple[List[SubtitleSegment], Optional[List[SubtitleSegment]]]:
        if not segments:
            return segments, translated

        order = sorted(
            range(len(segments)),
            key=lambda idx: (segments[idx].start, segments[idx].end),
        )
        sorted_segments = [segments[idx] for idx in order]

        if translated:
            sorted_translated: List[SubtitleSegment] = []
            for idx in order:
                if idx < len(translated):
                    sorted_translated.append(translated[idx])
            return sorted_segments, sorted_translated

        return sorted_segments, translated

    def _deduplicate_segments(
        self,
        segments: List[SubtitleSegment],
        translated: Optional[List[SubtitleSegment]],
    ) -> tuple[List[SubtitleSegment], Optional[List[SubtitleSegment]]]:
        if not segments:
            return segments, translated

        dedup_segments: List[SubtitleSegment] = []
        dedup_translations: List[SubtitleSegment] | None = [] if translated else None

        for idx, seg in enumerate(segments):
            if dedup_segments:
                prev = dedup_segments[-1]
                same_start = abs(prev.start - seg.start) < 0.05
                same_end = abs((prev.end or prev.start) - (seg.end or seg.start)) < 0.05
                text_prev = prev.text.strip()
                text_curr = seg.text.strip()
                text_prev_norm = self._normalise_overlap_text(text_prev)
                text_curr_norm = self._normalise_overlap_text(text_curr)
                text_redundant = (
                    text_prev == text_curr
                    or (text_curr and text_curr in text_prev)
                    or (text_prev and text_prev in text_curr)
                    or (text_curr_norm and text_curr_norm in text_prev_norm)
                    or (text_prev_norm and text_prev_norm in text_curr_norm)
                )
                overlapping = seg.start < prev.end and text_redundant

                if same_start and (same_end or seg.end >= prev.end):
                    replace = seg.end >= prev.end and len(text_curr) >= len(text_prev)
                    if replace:
                        dedup_segments[-1] = seg
                        if translated and idx < len(translated):
                            dedup_translations[-1] = translated[idx]
                    continue

                if overlapping:
                    replace = len(text_curr) > len(text_prev)
                    if replace:
                        dedup_segments[-1] = seg
                        if translated and idx < len(translated):
                            dedup_translations[-1] = translated[idx]
                    continue

            dedup_segments.append(seg)
            if dedup_translations is not None and translated and idx < len(translated):
                dedup_translations.append(translated[idx])

        if dedup_translations is not None:
            return dedup_segments, dedup_translations
        return dedup_segments, translated

    def _build_translation_summary(
        self,
        segment_count: int,
        usage: dict[str, dict[str, int]],
    ) -> str:
        base = f"翻译完成，处理 {segment_count} 条字幕"
        if not usage:
            return base
        return f"{base}，Token 消耗：{self._format_usage_summary(usage)}"

    def _format_usage_summary(self, usage: dict[str, dict[str, int]]) -> str:
        provider_labels = {
            "openai": "OpenAI",
            "grok": "Grok",
            "deepseek": "DeepSeek",
        }
        parts: list[str] = []
        for provider, stats in usage.items():
            label = provider_labels.get(provider, provider)
            requests = stats.get("requests", 0)
            input_tokens = stats.get("input_tokens", 0)
            output_tokens = stats.get("output_tokens", 0)
            parts.append(
                f"{label} 请求 {requests} 次，输入 {input_tokens}，输出 {output_tokens}"
            )
        return "; ".join(parts)

    def _should_apply_mecab(self, segments: List[WhisperSegmentResult]) -> bool:
        for segment in segments:
            if self._japanese_char_re.search(segment.text):
                return True
        return False

    def _filter_duplicate_whisper_segments(
        self,
        segments: List[WhisperSegmentResult],
    ) -> List[WhisperSegmentResult]:
        if not segments:
            return []

        filtered: List[WhisperSegmentResult] = []
        for seg in sorted(segments, key=lambda s: (s.start, s.end)):
            if filtered:
                prev = filtered[-1]
                same_start = abs(prev.start - seg.start) < 0.15
                same_end = abs(prev.end - seg.end) < 0.15
                text_prev = prev.text.strip()
                text_curr = seg.text.strip()
                text_prev_norm = self._normalise_overlap_text(text_prev)
                text_curr_norm = self._normalise_overlap_text(text_curr)

                if same_start and same_end:
                    if len(text_curr_norm) > len(text_prev_norm):
                        filtered[-1] = seg
                    continue

                if seg.start < prev.end:
                    if text_curr_norm and text_curr_norm in text_prev_norm:
                        continue
                    if text_prev_norm and text_prev_norm in text_curr_norm:
                        filtered[-1] = seg
                        continue
                    if text_curr and text_curr in text_prev:
                        continue
                    if text_prev and text_prev in text_curr:
                        filtered[-1] = seg
                        continue

            filtered.append(seg)
        return filtered

    def _normalise_overlap_text(self, value: str) -> str:
        if not value:
            return ""
        cleaned = self._overlap_cleanup_re.sub("", value)
        return cleaned.lower()
