from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .config import ServiceSettings
from .transcribe import WhisperSegmentResult

logger = logging.getLogger(__name__)

_JAPANESE_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
_ASCII_TOKEN_RE = re.compile(r"^[\x21-\x7e]+$")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([、。。，．！？!?])")
_MULTISPACE_RE = re.compile(r"\s{2,}")
_FULL_WIDTH_SPACE_RE = re.compile(r"[　]+")
_QUOTE_PUNCTUATION = {"」", "』", "】", "》", "〉", "≫", "』", "」", "】"}


@dataclass
class CorrectionSummary:
    total_segments: int
    corrected_segments: int


class MeCabTextCorrector:
    """Applies lightweight MeCab-based cleanup to Whisper segments."""

    def __init__(self, settings: ServiceSettings) -> None:
        self.settings = settings
        self.enabled: bool = bool(settings.enable_mecab_correction)
        self.status_message: str = "MeCab 校正已启用" if self.enabled else "MeCab 校正已通过配置禁用"
        self._tagger = None
        if not self.enabled:
            return

        try:
            import MeCab  # type: ignore
        except ImportError:
            logger.warning(
                "MeCabTextCorrector disabled: mecab-python3 is not installed.",
            )
            self.enabled = False
            self.status_message = "MeCab 校正不可用：未安装 mecab-python3"
            return

        args: List[str] = []
        if settings.mecab_dictionary_path:
            args.extend(["-d", str(settings.mecab_dictionary_path)])
        if settings.mecab_user_dictionary_path:
            args.extend(["-u", str(settings.mecab_user_dictionary_path)])

        if settings.mecab_rc_path:
            os.environ.setdefault("MECABRC", str(settings.mecab_rc_path))
        else:
            for candidate in (
                Path("/opt/homebrew/etc/mecabrc"),
                Path("/usr/local/etc/mecabrc"),
                Path("/etc/mecabrc"),
            ):
                if candidate.exists():
                    os.environ.setdefault("MECABRC", str(candidate))
                    break

        arg_string = " ".join(args)
        try:
            self._tagger = MeCab.Tagger(arg_string) if arg_string else MeCab.Tagger()
            # Prevent MeCab object from being garbage collected prematurely.
            self._tagger.parse("")  # type: ignore[func-returns-value]
            self.status_message = "MeCab 校正已启用"
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to initialise MeCab tagger: %s", exc)
            self.enabled = False
            self._tagger = None
            self.status_message = f"MeCab 校正不可用：初始化失败（{exc}）"

    def correct_segments(
        self,
        segments: Iterable[WhisperSegmentResult],
    ) -> Tuple[List[WhisperSegmentResult], Optional[CorrectionSummary]]:
        if not self.enabled or not self._tagger:
            return list(segments), None

        corrected_segments: List[WhisperSegmentResult] = []
        changes = 0

        for segment in segments:
            corrected_text = self._correct_text(segment.text)
            if corrected_text != segment.text:
                changes += 1
            corrected_segments.append(
                WhisperSegmentResult(
                    start=segment.start,
                    end=segment.end,
                    text=corrected_text,
                    language=segment.language,
                )
            )

        summary = CorrectionSummary(
            total_segments=len(corrected_segments),
            corrected_segments=changes,
        )
        return corrected_segments, summary

    def _correct_text(self, text: str) -> str:
        if not text.strip():
            return text

        normalised = unicodedata.normalize("NFKC", text)
        normalised = _FULL_WIDTH_SPACE_RE.sub(" ", normalised)
        if not _JAPANESE_CHAR_RE.search(normalised):
            return normalised.strip()

        node = self._tagger.parseToNode(normalised)  # type: ignore[attr-defined]
        pieces: List[str] = []
        prev_ascii = False

        while node:
            surface = node.surface
            node = node.next
            if not surface:
                continue

            is_ascii = bool(_ASCII_TOKEN_RE.fullmatch(surface))
            punctuation = surface in _QUOTE_PUNCTUATION or _SPACE_BEFORE_PUNCT_RE.match(surface)

            if pieces:
                if is_ascii:
                    if not prev_ascii:
                        pieces.append(" ")
                elif prev_ascii and not punctuation:
                    pieces.append(" ")

            pieces.append(surface)
            prev_ascii = is_ascii

        corrected = "".join(pieces)
        corrected = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", corrected)
        corrected = _MULTISPACE_RE.sub(" ", corrected)
        return corrected.strip()
