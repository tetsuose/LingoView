from __future__ import annotations

from pathlib import Path

from lingoview_service.config import ServiceSettings
from lingoview_service.exports import compute_source_hash, prepare_and_save_exports
from lingoview_service.pipeline import SubtitleResult, SubtitleSegment


def test_prepare_and_save_exports(tmp_path: Path) -> None:
    settings = ServiceSettings(
        grok_api_key="test-grok",
        storage_dir=tmp_path,
        whisper_model="tiny",
        whisper_device="cpu",
        whisper_compute_type="int8",
    )
    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"fake")

    result = SubtitleResult(
        segments=[SubtitleSegment(start=0.0, end=1.0, text="hello")],
        language="en",
        translated_segments=[SubtitleSegment(start=0.0, end=1.0, text="你好")],
        translation_language="zh",
    )

    source_hash = compute_source_hash(media_path)
    exports = prepare_and_save_exports(
        result,
        settings=settings,
        source_hash=source_hash,
        original_name=media_path.name,
    )

    assert "srt_original" in exports
    assert Path(exports["srt_original"]["path"]).exists()
    assert "你好" in (exports["json_translation"]["content"] if "json_translation" in exports else "")
    assert "metadata" in exports
    metadata_path = Path(exports["metadata"]["path"])
    assert metadata_path.exists()
