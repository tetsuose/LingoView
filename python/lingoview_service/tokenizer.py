from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

try:
    import sudachipy.tokenizer as sudachi_tokenizer
    from sudachipy import dictionary as sudachi_dictionary
except ImportError:  # pragma: no cover - optional dependency
    sudachi_tokenizer = None
    sudachi_dictionary = None

try:
    import fugashi
except ImportError:  # pragma: no cover - optional dependency
    fugashi = None

try:
    from pykakasi import kakasi as kakasi_factory
except ImportError:  # pragma: no cover - optional dependency
    kakasi_factory = None

from .config import ServiceSettings


@dataclass
class TokenDetail:
    surface: str
    reading: Optional[str] = None
    romaji: Optional[str] = None

class LingoViewTokenizer(ABC):
    @abstractmethod
    def tokenize(self, text: str, language: str) -> List[TokenDetail]:
        raise NotImplementedError


class SudachiTokenizer(LingoViewTokenizer):
    def __init__(self, mode: str = "C") -> None:
        if not sudachi_dictionary:
            raise RuntimeError("SudachiPy is not installed")
        self.mode = {
            "A": sudachi_tokenizer.Tokenizer.SplitMode.A,
            "B": sudachi_tokenizer.Tokenizer.SplitMode.B,
            "C": sudachi_tokenizer.Tokenizer.SplitMode.C,
        }.get(mode.upper(), sudachi_tokenizer.Tokenizer.SplitMode.C)
        self.tokenizer = sudachi_dictionary.Dictionary().create()
        self.kakasi = None
        if kakasi_factory:
            self.kakasi = kakasi_factory()
            self.kakasi.setMode("H", "a")
            self.kakasi.setMode("K", "a")
            self.kakasi.setMode("J", "a")
            self.kakasi.setMode("r", "Hepburn")
            self.kakasi.setMode("s", True)
            self.kakasi.setMode("C", True)
            self.converter = self.kakasi.getConverter()
        else:
            self.converter = None

    def tokenize(self, text: str, language: str) -> List[TokenDetail]:
        if language.startswith("ja"):
            items: List[TokenDetail] = []
            for morpheme in self.tokenizer.tokenize(text, self.mode):
                surface = morpheme.surface()
                reading_form = morpheme.reading_form() or None
                if reading_form in {"*", ""}:
                    reading_form = None
                romaji = None
                if reading_form and self.converter:
                    romaji = self.converter.do(reading_form)
                items.append(TokenDetail(surface=surface, reading=reading_form, romaji=romaji))
            return items
        return [TokenDetail(surface=token) for token in text.split() if token]


class FugashiTokenizer(LingoViewTokenizer):
    def __init__(self) -> None:
        if not fugashi:
            raise RuntimeError("fugashi is not installed")
        self.tagger = fugashi.Tagger()
        if kakasi_factory:
            kakasi_inst = kakasi_factory()
            kakasi_inst.setMode("H", "a")
            kakasi_inst.setMode("K", "a")
            kakasi_inst.setMode("J", "a")
            kakasi_inst.setMode("r", "Hepburn")
            kakasi_inst.setMode("s", True)
            kakasi_inst.setMode("C", True)
            self.converter = kakasi_inst.getConverter()
        else:
            self.converter = None

    def tokenize(self, text: str, language: str) -> List[TokenDetail]:
        if language.startswith("ja"):
            items: List[TokenDetail] = []
            for word in self.tagger(text):
                reading = None
                if hasattr(word, "feature") and hasattr(word.feature, "kana"):
                    reading = word.feature.kana or None
                    if reading in {"*", ""}:
                        reading = None
                romaji = None
                if reading and self.converter:
                    romaji = self.converter.do(reading)
                items.append(TokenDetail(surface=word.surface, reading=reading, romaji=romaji))
            return items
        return [TokenDetail(surface=token) for token in text.split() if token]


class WhitespaceTokenizer(LingoViewTokenizer):
    def tokenize(self, text: str, language: str) -> List[TokenDetail]:
        return [TokenDetail(surface=token) for token in text.split() if token]


def get_tokenizer(settings: ServiceSettings) -> LingoViewTokenizer:
    backend = settings.tokenizer_backend.lower()
    if backend == "sudachi":
        return SudachiTokenizer(mode=settings.sudachi_mode)
    if backend == "fugashi":
        return FugashiTokenizer()
    return WhitespaceTokenizer()
