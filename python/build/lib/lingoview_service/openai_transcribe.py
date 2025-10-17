from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Callable, List, Optional

import requests

from .config import ServiceSettings
from .transcribe import WhisperSegmentResult


class OpenAIWhisperError(RuntimeError):
    """Raised when the OpenAI Whisper API request fails."""


class OpenAIWhisperClient:
    """Client that sends audio to OpenAI's whisper-1 API and returns segments."""

    def __init__(self, settings: ServiceSettings) -> None:
        self.settings = settings
        api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when whisper_backend=openai")
        self.api_key = api_key
        self.api_base = (settings.openai_api_base or "https://api.openai.com/v1").rstrip("/")
        self.model = settings.openai_whisper_model
        self.timeout = settings.openai_timeout

    async def transcribe(
        self,
        media_path: Path,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> List[WhisperSegmentResult]:
        return await asyncio.to_thread(self._transcribe_sync, media_path)

    def _transcribe_sync(self, media_path: Path) -> List[WhisperSegmentResult]:
        url = f"{self.api_base}/audio/transcriptions"
        with media_path.open("rb") as fp:
            files = {"file": (media_path.name, fp, "application/octet-stream")}
            data = {
                "model": self.model,
                "response_format": "verbose_json",
                "temperature": str(self.settings.whisper_temperature),
            }
            if self.settings.whisper_language:
                data["language"] = self.settings.whisper_language

            headers = {"Authorization": f"Bearer {self.api_key}"}

            try:
                response = requests.post(
                    url,
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:  # pragma: no cover - network failure
                raise OpenAIWhisperError(f"Failed to call OpenAI Whisper API: {exc}") from exc

        if response.status_code != 200:
            raise OpenAIWhisperError(
                f"OpenAI Whisper API error {response.status_code}: {response.text[:512]}"
            )

        payload = response.json()
        segments_data = payload.get("segments")
        if not segments_data:
            text = payload.get("text", "").strip()
            if not text:
                return []
            duration = payload.get("duration")
            return [
                WhisperSegmentResult(
                    start=0.0,
                    end=duration or 0.0,
                    text=text,
                    language=payload.get("language", "und"),
                )
            ]

        language = payload.get("language", "und")
        segments: List[WhisperSegmentResult] = []
        for seg in segments_data:
            text = seg.get("text", "").strip()
            if not text:
                continue
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
            seg_language = seg.get("language", language) or language
            segments.append(
                WhisperSegmentResult(start=start, end=end, text=text, language=seg_language)
            )
        return segments
