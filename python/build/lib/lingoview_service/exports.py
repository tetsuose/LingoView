from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json

from .config import ServiceSettings
from .formats import build_json, build_srt
from .pipeline import SubtitleResult, SubtitleSegment


def compute_source_hash(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def prepare_and_save_exports(
    result: SubtitleResult,
    settings: ServiceSettings,
    source_hash: str,
    original_name: str,
) -> Dict[str, dict[str, str | Path]]:
    """Persist subtitles to disk and return mapping for downloads."""

    exports_dir = settings.storage_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    media_stem = (Path(original_name).stem or "output").replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = exports_dir / f"{media_stem}-{timestamp}"

    outputs: Dict[str, dict[str, str | Path]] = {
        "srt_original": {
            "path": base.with_suffix(".original.srt"),
            "content": build_srt(result.segments),
        },
        "json_original": {
            "path": base.with_suffix(".original.json"),
            "content": build_json(result, use_translation=False),
        },
    }

    if result.translated_segments:
        outputs["srt_translation"] = {
            "path": base.with_suffix(".translation.srt"),
            "content": build_srt(result.translated_segments),
        }
        outputs["json_translation"] = {
            "path": base.with_suffix(".translation.json"),
            "content": build_json(result, use_translation=True),
        }

    for entry in outputs.values():
        path = entry["path"]
        content = entry["content"]
        assert isinstance(path, Path)
        assert isinstance(content, str)
        path.write_text(content, encoding="utf-8")

    metadata_path = base.with_suffix(".metadata.json")

    metadata = {
        "media": str(original_name),
        "timestamp": timestamp,
        "sourceHash": source_hash,
        "language": result.language,
        "translationLanguage": result.translation_language,
        "segments": [_segment_to_dict(segment) for segment in result.segments],
        "translatedSegments": [
            _segment_to_dict(segment) for segment in (result.translated_segments or [])
        ],
        "exports": {
            key: {"name": Path(value["path"]).name, "path": str(value["path"])}
            for key, value in outputs.items()
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    outputs["metadata"] = {"path": metadata_path, "content": json.dumps(metadata)}

    return outputs


def list_exports(settings: ServiceSettings, limit: int = 10) -> List[dict]:
    exports_dir = settings.storage_dir / "exports"
    if not exports_dir.exists():
        return []

    metadata_files = sorted(exports_dir.glob("*.metadata.json"), reverse=True)
    items = []
    for path in metadata_files[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["metadataFile"] = str(path)
            items.append(data)
        except json.JSONDecodeError:
            continue
    return items


def _segment_to_dict(segment: SubtitleSegment) -> dict:
    return {
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


def find_cached_result(
    settings: ServiceSettings,
    source_hash: str,
    target_language: Optional[str],
) -> Optional[Tuple[dict, Path]]:
    exports_dir = settings.storage_dir / "exports"
    if not exports_dir.exists():
        return None

    normalized_target = (target_language or "").strip().lower()

    metadata_files = sorted(exports_dir.glob("*.metadata.json"), reverse=True)
    for metadata_path in metadata_files:
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        if data.get("sourceHash") != source_hash:
            continue

        candidate_language = (data.get("translationLanguage") or "").strip().lower()
        if candidate_language != normalized_target:
            continue

        return data, metadata_path

    return None
