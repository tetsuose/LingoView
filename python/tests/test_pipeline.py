from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lingoview_service.config import ServiceSettings
from lingoview_service.pipeline import SubtitlePipeline, SubtitleSegment, SubtitleResult
from lingoview_service.transcribe import WhisperSegmentResult
from lingoview_service.transcribe import WhisperSegmentResult
from lingoview_service.tokenizer import WhitespaceTokenizer


class DummyWhisper:
    def __init__(self, segments: list[WhisperSegmentResult]) -> None:
        self._segments = segments
        self.media_paths: list[Path] = []

    async def transcribe(self, media_path: Path, progress_cb=None):
        self.media_paths.append(media_path)
        if progress_cb:
            progress_cb(len(self._segments), len(self._segments))
        return self._segments


class DummyTranslator:
    def __init__(self, prefix: str = "TRANS") -> None:
        self.prefix = prefix
        self.seen_contexts: list = []
        self.begin_called = 0
        self.end_called = 0

    async def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: str | None = None,
        context=None,
    ) -> str:
        self.seen_contexts.append(context)
        return f"{self.prefix}:{target_language}:{text}"

    def begin_usage_session(self) -> None:
        self.begin_called += 1

    def end_usage_session(self) -> dict:
        self.end_called += 1
        return {}


@pytest.fixture()
def base_settings(tmp_path: Path) -> ServiceSettings:
    settings = ServiceSettings(
        grok_api_key="test-grok",
        storage_dir=tmp_path,
        whisper_model="tiny",
        whisper_device="cpu",
        whisper_compute_type="int8",
    )
    settings.enable_vocal_separation = False
    return settings


def test_pipeline_preserves_whisper_segments(base_settings: ServiceSettings) -> None:
    whisper_segments = [
        WhisperSegmentResult(start=0.0, end=30.0, text="Sentence one. Sentence two!", language="en"),
    ]
    pipeline = SubtitlePipeline(
        settings=base_settings,
        whisper_client=DummyWhisper(whisper_segments),
        translator_client=DummyTranslator(),
        tokenizer=WhitespaceTokenizer(),
    )

    result = pipeline.run_sync(media_path=base_settings.storage_dir / "dummy.mp4")

    assert len(result.segments) == 1
    assert result.segments[0].text == "Sentence one. Sentence two!"
    assert result.segments[0].start == 0.0
    assert [token.surface for token in result.segments[0].tokens or []] == [
        "Sentence",
        "one.",
        "Sentence",
        "two!",
    ]


def test_generate_includes_translation(base_settings: ServiceSettings) -> None:
    whisper_segments = [
        WhisperSegmentResult(start=0.0, end=5.0, text="Hello world.", language="en"),
    ]
    translator = DummyTranslator(prefix="JA")
    pipeline = SubtitlePipeline(
        settings=base_settings,
        whisper_client=DummyWhisper(whisper_segments),
        translator_client=translator,
        tokenizer=WhitespaceTokenizer(),
    )

    result = pipeline.run_sync(media_path=base_settings.storage_dir / "dummy.mp3", target_language="ja")

    assert result.translation_language == "ja"
    assert result.translated_segments is not None
    assert result.translated_segments[0].text == "JA:ja:Hello world."
    assert [token.surface for token in result.segments[0].tokens or []] == ["Hello", "world."]
    assert translator.seen_contexts
    ctx = translator.seen_contexts[0]
    assert getattr(ctx, "title", None) == "dummy"


def test_language_normalisation_limits_to_en_or_ja(base_settings: ServiceSettings) -> None:
    pipeline = SubtitlePipeline(
        settings=base_settings,
        whisper_client=DummyWhisper([]),
        translator_client=DummyTranslator(),
        tokenizer=WhitespaceTokenizer(),
    )

    segments = [
        WhisperSegmentResult(start=0.0, end=1.0, text="これはテスト", language="ko"),
        WhisperSegmentResult(start=1.0, end=2.0, text="This is a test", language="fr"),
    ]

    normalised = pipeline._normalise_segment_languages(segments)
    primary = pipeline._determine_primary_language(normalised)
    assert primary == "ja"
    coerced = [
        WhisperSegmentResult(seg.start, seg.end, seg.text, primary)
        for seg in normalised
    ]
    assert all(segment.language == "ja" for segment in coerced)


def test_primary_language_enforces_first_detected_language(base_settings: ServiceSettings) -> None:
    pipeline = SubtitlePipeline(
        settings=base_settings,
        whisper_client=DummyWhisper([]),
        translator_client=DummyTranslator(),
        tokenizer=WhitespaceTokenizer(),
    )

    segments = [
        WhisperSegmentResult(start=0.0, end=1.0, text="This is English", language="fr"),
        WhisperSegmentResult(start=1.0, end=2.0, text="これはテスト", language="ja"),
    ]

    normalised = pipeline._normalise_segment_languages(segments)
    primary = pipeline._determine_primary_language(normalised)
    assert primary == "en"


def test_pipeline_invokes_vocal_separation(monkeypatch, base_settings: ServiceSettings) -> None:
    base_settings.enable_vocal_separation = True
    whisper_segments = [
        WhisperSegmentResult(start=0.0, end=1.0, text="テスト", language="ja"),
    ]
    whisper = DummyWhisper(whisper_segments)
    pipeline = SubtitlePipeline(
        settings=base_settings,
        whisper_client=whisper,
        translator_client=DummyTranslator(),
        tokenizer=WhitespaceTokenizer(),
    )

    processed_path = base_settings.storage_dir / "processed.wav"

    def fake_separate(media_path: Path, settings):
        return processed_path

    monkeypatch.setattr("lingoview_service.pipeline.separate_vocals", fake_separate)

    pipeline.run_sync(media_path=base_settings.storage_dir / "input.wav")

    assert whisper.media_paths[0] == processed_path


def test_segments_are_sorted_by_start(base_settings: ServiceSettings) -> None:
    pipeline = SubtitlePipeline(
        settings=base_settings,
        whisper_client=DummyWhisper([]),
        translator_client=DummyTranslator(),
        tokenizer=WhitespaceTokenizer(),
    )

    segments = [
        SubtitleSegment(start=5.0, end=6.0, text="second"),
        SubtitleSegment(start=1.0, end=2.0, text="first"),
    ]
    translations = [
        SubtitleSegment(start=5.0, end=6.0, text="第二"),
        SubtitleSegment(start=1.0, end=2.0, text="第一"),
    ]

    ordered_segments, ordered_translations = pipeline._sort_segments_with_translations(segments, translations)

    assert [segment.text for segment in ordered_segments] == ["first", "second"]
    assert ordered_translations is not None
    assert [segment.text for segment in ordered_translations] == ["第一", "第二"]


def test_deduplicate_segments_removes_subset_entries(base_settings: ServiceSettings) -> None:
    pipeline = SubtitlePipeline(
        settings=base_settings,
        whisper_client=DummyWhisper([]),
        translator_client=DummyTranslator(),
        tokenizer=WhitespaceTokenizer(),
    )

    segments = [
        SubtitleSegment(start=18.0, end=19.0, text="下回，ONE PIECE！"),
        SubtitleSegment(start=18.0, end=25.0, text="下回，一件，独裁乔巴的冒险病历，背叛者们的化装舞会。"),
    ]
    translations = [
        SubtitleSegment(start=18.0, end=19.0, text="Next time, ONE PIECE!"),
        SubtitleSegment(start=18.0, end=25.0, text="Next time, Chopper's adventure medical record."),
    ]

    sorted_segments, sorted_translations = pipeline._deduplicate_segments(segments, translations)

    assert len(sorted_segments) == 1
    assert sorted_segments[0].text.startswith("下回，一件")
    assert sorted_translations is not None
    assert len(sorted_translations) == 1


class DummyRemoteWhisper:
    def __init__(self) -> None:
        self.called = False

    async def transcribe(self, media_path: Path, progress_cb=None):
        self.called = True
        return [
            WhisperSegmentResult(start=0.0, end=2.0, text="Hello world", language="en")
        ]


def test_pipeline_openai_backend(monkeypatch, tmp_path: Path) -> None:
    settings = ServiceSettings(
        storage_dir=tmp_path,
        whisper_backend="openai",
        openai_api_key="sk-test",
        enable_vocal_separation=False,
    )
    dummy_remote = DummyRemoteWhisper()
    pipeline = SubtitlePipeline(
        settings=settings,
        whisper_client=dummy_remote,
        translator_client=DummyTranslator(),
        tokenizer=WhitespaceTokenizer(),
    )
    result = pipeline.run_sync(media_path=tmp_path / "fake.mp4")

    assert dummy_remote.called
    assert len(result.segments) == 1
    assert result.segments[0].text == "Hello world"
