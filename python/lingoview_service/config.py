from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, HttpUrl, field_validator
from pydantic.networks import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Runtime configuration for the LingoView Python backend."""

    grok_api_key: Optional[str] = Field(None, env="GROK_API_KEY")
    grok_model: str = Field("grok-4-latest", env="GROK_MODEL")
    grok_endpoint: HttpUrl = Field("https://api.x.ai/v1/chat/completions", env="GROK_ENDPOINT")

    deepseek_api_key: Optional[str] = Field(None, env="DEEPSEEK_API_KEY")
    deepseek_model: str = Field("deepseek-chat", env="DEEPSEEK_MODEL")
    deepseek_endpoint: HttpUrl = Field("https://api.deepseek.com/chat/completions", env="DEEPSEEK_ENDPOINT")

    translator_provider: str = Field("gpt", env="TRANSLATOR_PROVIDER")
    openai_translate_model: str = Field("gpt-4.1-mini", env="OPENAI_TRANSLATE_MODEL")
    openai_translate_endpoint: Optional[AnyHttpUrl] = Field(None, env="OPENAI_TRANSLATE_ENDPOINT")
    openai_translate_timeout: int = Field(120, env="OPENAI_TRANSLATE_TIMEOUT")

    whisper_backend: str = Field("local", env="WHISPER_BACKEND")
    whisper_model: str = Field("small", env="WHISPER_MODEL")
    whisper_device: str = Field("auto", env="WHISPER_DEVICE")
    whisper_compute_type: str = Field("float32", env="WHISPER_COMPUTE_TYPE")
    whisper_beam_size: int = Field(5, env="WHISPER_BEAM_SIZE")
    whisper_language: Optional[str] = Field(None, env="WHISPER_LANGUAGE")
    whisper_temperature: float = Field(0.2, env="WHISPER_TEMPERATURE")
    whisper_no_speech_threshold: float = Field(0.6, env="WHISPER_NO_SPEECH_THRESHOLD")
    whisper_log_prob_threshold: float = Field(-1.0, env="WHISPER_LOG_PROB_THRESHOLD")
    whisper_compression_ratio_threshold: float = Field(
        2.4, env="WHISPER_COMPRESSION_RATIO_THRESHOLD"
    )
    whisper_condition_on_previous_text: bool = Field(
        True, env="WHISPER_CONDITION_ON_PREVIOUS_TEXT"
    )

    storage_dir: Path = Field(Path.home() / ".cache" / "lingoview", env="LINGOVIEW_STORAGE_DIR")
    cache_audio: bool = Field(True, env="CACHE_AUDIO")
    max_parallel_requests: int = Field(4, env="MAX_PARALLEL_REQUESTS")
    chunk_seconds: int = Field(120, env="WHISPER_CHUNK_SECONDS")
    chunk_overlap: float = Field(1.0, env="WHISPER_CHUNK_OVERLAP")

    sudachi_mode: str = Field("C", env="SUDACHI_MODE")
    tokenizer_backend: str = Field("sudachi", env="LINGOVIEW_TOKENIZER")
    enable_mecab_correction: bool = Field(True, env="ENABLE_MECAB_CORRECTION")
    mecab_dictionary_path: Optional[Path] = Field(None, env="MECAB_DICTIONARY_PATH")
    mecab_user_dictionary_path: Optional[Path] = Field(None, env="MECAB_USER_DICTIONARY_PATH")
    mecab_rc_path: Optional[Path] = Field(None, env="MECABRC")

    enable_vocal_separation: bool = Field(True, env="ENABLE_VOCAL_SEPARATION")
    demucs_model: str = Field("htdemucs", env="DEMUCS_MODEL")
    demucs_executable: str = Field("demucs", env="DEMUCS_EXECUTABLE")
    enable_vad: bool = Field(True, env="ENABLE_VAD")
    vad_split_silence_ms: int = Field(2000, env="VAD_SPLIT_SILENCE_MS")

    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    openai_api_base: Optional[AnyHttpUrl] = Field(None, env="OPENAI_API_BASE")
    openai_whisper_model: str = Field("whisper-1", env="OPENAI_WHISPER_MODEL")
    openai_timeout: int = Field(300, env="OPENAI_WHISPER_TIMEOUT")

    model_config = SettingsConfigDict(
        env_file=(
            Path(__file__).resolve().parents[2] / ".env",
            Path(__file__).resolve().parents[1] / ".env",
            ".env",
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("whisper_beam_size")
    def _validate_beam_size(cls, value: int) -> int:
        return max(1, min(value, 10))

    @field_validator("whisper_temperature")
    def _validate_temperature(cls, value: float) -> float:
        return max(0.0, min(value, 1.0))

    @field_validator("whisper_no_speech_threshold")
    def _validate_no_speech(cls, value: float) -> float:
        return max(0.0, min(value, 1.0))

    @field_validator("whisper_log_prob_threshold")
    def _validate_log_prob(cls, value: float) -> float:
        return min(0.0, value)

    @field_validator("whisper_compression_ratio_threshold")
    def _validate_compression(cls, value: float) -> float:
        return max(0.0, value)

    @field_validator("whisper_language", mode="before")
    def _normalize_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("max_parallel_requests")
    def _validate_parallel(cls, value: int) -> int:
        return max(1, min(value, 16))

    @field_validator("chunk_seconds")
    def _validate_chunk_seconds(cls, value: int) -> int:
        return max(30, value)

    @field_validator("chunk_overlap")
    def _validate_overlap(cls, value: float) -> float:
        return max(0.0, min(value, 30.0))

    @field_validator("storage_dir", mode="before")
    def _coerce_storage(cls, value: Path | str) -> Path:
        if isinstance(value, Path):
            path = value
        else:
            cleaned = value.strip().strip('"').strip("'")
            expanded_str = cleaned.replace("$HOME", str(Path.home()))
            expanded_str = os.path.expandvars(expanded_str)
            path = Path(expanded_str).expanduser()
        path = path.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @field_validator(
        "mecab_dictionary_path",
        "mecab_user_dictionary_path",
        "mecab_rc_path",
        mode="before",
    )
    def _coerce_optional_path(
        cls,
        value: Path | str | None,
    ) -> Optional[Path]:
        if value is None:
            return None
        if isinstance(value, Path):
            return value.expanduser().resolve()
        cleaned = value.strip().strip('"').strip("'")
        if not cleaned:
            return None
        expanded = cleaned.replace("$HOME", str(Path.home()))
        expanded = os.path.expandvars(expanded)
        return Path(expanded).expanduser().resolve()

    @field_validator("vad_split_silence_ms")
    def _validate_vad_split(cls, value: int) -> int:
        return max(0, value)

    @field_validator("translator_provider")
    def _validate_provider(cls, value: str) -> str:
        cleaned = (value or "auto").strip().lower()
        if cleaned == "auto":
            return "auto"
        if cleaned not in {"deepseek", "grok"}:
            return "auto"
        return cleaned


@lru_cache(maxsize=1)
def load_settings() -> ServiceSettings:
    """Singleton accessor for service settings."""

    return ServiceSettings()


def ensure_env_var(name: str) -> str:
    try:
        return os.environ[name]
    except KeyError as exc:  # pragma: no cover - simple helper
        raise RuntimeError(f"Missing required environment variable: {name}") from exc
