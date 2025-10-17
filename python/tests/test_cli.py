from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lingoview_service import cli
from lingoview_service.pipeline import SubtitleResult, SubtitleSegment
from lingoview_service.tokenizer import TokenDetail


class DummyPipeline:
    def __init__(self, settings) -> None:  # noqa: D401 - signature matches real pipeline
        self.settings = settings

    async def generate(self, media_path: Path, translate_to: str | None, media_title: str | None = None):
        segments = [
            SubtitleSegment(start=0.0, end=1.0, text="hello", tokens=[TokenDetail(surface="hello")]),
        ]
        translated = None
        if translate_to:
            translated = [
                SubtitleSegment(
                    start=0.0,
                    end=1.0,
                    text="你好",
                    tokens=[TokenDetail(surface="你好")],
                )
            ]
        return SubtitleResult(
            segments=segments,
            language="en",
            translated_segments=translated,
            translation_language=translate_to,
        )


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GROK_API_KEY", "test-grok")
    monkeypatch.setenv("LINGOVIEW_STORAGE_DIR", str(tmp_path))


def test_cli_transcribe_creates_outputs(monkeypatch, tmp_path: Path):
    media_file = tmp_path / "media.mp4"
    media_file.write_bytes(b"fake")

    monkeypatch.setattr(cli, "SubtitlePipeline", DummyPipeline)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "transcribe",
            str(media_file),
            "--translate",
            "zh",
            "--json-output",
            str(tmp_path / "out.json"),
            "--srt-output",
            str(tmp_path / "out.srt"),
        ],
    )

    assert result.exit_code == 0
    json_path = tmp_path / "out.json"
    srt_path = tmp_path / "out.srt"
    assert json_path.exists()
    assert srt_path.exists()
    payload = json.loads(json_path.read_text("utf-8"))
    assert payload["segments"][0]["text"] == "hello"
    assert "hello" in srt_path.read_text("utf-8")


def test_cli_transcribe_translation_output(monkeypatch, tmp_path: Path):
    media_file = tmp_path / "media.mkv"
    media_file.write_bytes(b"fake")

    monkeypatch.setattr(cli, "SubtitlePipeline", DummyPipeline)

    runner = CliRunner()
    json_path = tmp_path / "out-translation.json"
    result = runner.invoke(
        cli.app,
        [
            "transcribe",
            str(media_file),
            "--translate",
            "zh",
            "--json-output",
            str(json_path),
            "--srt-output",
            str(tmp_path / "out-translation.srt"),
            "--srt-source",
            "translation",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(json_path.read_text("utf-8"))
    assert payload["segments"][0]["text"] == "你好"
