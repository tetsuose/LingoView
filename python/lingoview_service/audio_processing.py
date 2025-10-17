from __future__ import annotations

import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checking only
    from .config import ServiceSettings


class VocalSeparationError(RuntimeError):
    """Raised when Demucs-based vocal separation fails."""


def _compute_media_hash(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def separate_vocals(media_path: Path, settings: "ServiceSettings") -> Path:
    """Run Demucs vocal separation if enabled, returning path to vocals-only audio."""

    if not settings.enable_vocal_separation:
        return media_path

    cache_root = settings.storage_dir / "demucs"
    cache_root.mkdir(parents=True, exist_ok=True)

    media_hash = _compute_media_hash(media_path)
    cached_path = cache_root / f"{media_hash}-vocals.wav"
    if cached_path.exists():
        return cached_path

    tmp_output = cache_root / f"tmp-{media_hash}"
    if tmp_output.exists():
        shutil.rmtree(tmp_output, ignore_errors=True)
    tmp_output.mkdir(parents=True, exist_ok=True)

    cmd = [
        settings.demucs_executable,
        "--two-stems=vocals",
        "-n",
        settings.demucs_model,
        "-o",
        str(tmp_output),
        str(media_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment dependent
        raise VocalSeparationError(
            "Demucs executable not found. Install demucs (pip install demucs) or set DEMUCS_EXECUTABLE."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="ignore").strip()
        raise VocalSeparationError(f"Demucs separation failed: {stderr[:400]}") from exc

    # locate vocals file
    vocals_path: Path | None = None
    for candidate in tmp_output.rglob("vocals.*"):
        if candidate.is_file():
            vocals_path = candidate
            break

    if vocals_path is None:
        stdout = result.stdout.decode(errors="ignore").strip()
        stderr = result.stderr.decode(errors="ignore").strip()
        raise VocalSeparationError(
            "Demucs did not produce vocals output.\n"
            f"stdout: {stdout[:400]}\n"
            f"stderr: {stderr[:400]}"
        )

    shutil.move(str(vocals_path), cached_path)
    shutil.rmtree(tmp_output, ignore_errors=True)
    return cached_path
