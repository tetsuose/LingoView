from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Dict, Optional

import httpx
from openai import AsyncOpenAI

from .config import ServiceSettings


@dataclass(slots=True)
class TranslationContext:
    """Additional hints that help LLM-based translators stay consistent."""

    title: Optional[str] = None
    previous_text: Optional[str] = None
    next_text: Optional[str] = None
    segment_index: Optional[int] = None
    total_segments: Optional[int] = None


class TranslatorClient:
    def __init__(self, settings: ServiceSettings) -> None:
        timeout = httpx.Timeout(120.0, connect=30.0, read=120.0, write=120.0, pool=30.0)
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=timeout)
        self._usage_totals: Dict[str, Dict[str, int]] = {}
        self._session_usage: Dict[str, Dict[str, int]] | None = None
        api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
        base_url = settings.openai_translate_endpoint or settings.openai_api_base
        self._openai_client: AsyncOpenAI | None = None
        if api_key:
            self._openai_client = AsyncOpenAI(api_key=api_key, base_url=str(base_url) if base_url else None)
        self._openai_timeout = settings.openai_translate_timeout

    async def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: str | None = None,
        context: TranslationContext | None = None,
    ) -> str:
        if not text.strip():
            return ""

        provider = self.settings.translator_provider

        if provider == "auto":
            if self._openai_client:
                try:
                    return await self._translate_with_openai(text, target_language, source_language, context)
                except Exception:
                    pass
            if self.settings.grok_api_key:
                try:
                    return await self._translate_with_grok(text, target_language, source_language, context)
                except Exception:
                    if not self.settings.deepseek_api_key:
                        raise
            provider = "deepseek"

        if provider in {"gpt", "openai"}:
            if self._openai_client:
                try:
                    return await self._translate_with_openai(text, target_language, source_language, context)
                except Exception:
                    if self.settings.grok_api_key:
                        provider = "grok"
                    else:
                        provider = "deepseek"
            else:
                provider = "grok" if self.settings.grok_api_key else "deepseek"

        if provider == "grok":
            if self.settings.grok_api_key:
                return await self._translate_with_grok(text, target_language, source_language, context)
            if self.settings.deepseek_api_key:
                return await self._translate_with_deepseek(text, target_language, source_language, context)
            return text

        if provider == "deepseek":
            if self.settings.deepseek_api_key:
                return await self._translate_with_deepseek(text, target_language, source_language, context)
            if self.settings.grok_api_key:
                return await self._translate_with_grok(text, target_language, source_language, context)
            return text

        if self.settings.grok_api_key:
            return await self._translate_with_grok(text, target_language, source_language, context)
        if self.settings.deepseek_api_key:
            return await self._translate_with_deepseek(text, target_language, source_language, context)

        # 无可用翻译服务时直接返回原文
        return text

    def begin_usage_session(self) -> None:
        self._session_usage = {}

    def end_usage_session(self) -> Dict[str, Dict[str, int]]:
        if self._session_usage is None:
            return {}
        snapshot = {provider: stats.copy() for provider, stats in self._session_usage.items()}
        self._session_usage = None
        return snapshot

    def get_usage_totals(self) -> Dict[str, Dict[str, int]]:
        return {provider: stats.copy() for provider, stats in self._usage_totals.items()}

    async def _translate_with_openai(
        self,
        text: str,
        target_language: str,
        source_language: str | None,
        context: TranslationContext | None,
    ) -> str:
        if not self._openai_client:
            raise RuntimeError("OpenAI translate client not configured")

        system_prompt, user_prompt = self._compose_prompts(text, target_language, source_language, context)
        try:
            response = await self._openai_client.responses.create(
                model=self.settings.openai_translate_model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=self._openai_timeout,
            )
        except Exception:
            self._record_usage("openai")
            raise

        output_text = getattr(response, "output_text", None)
        if not output_text:
            parts: list[str] = []
            output = getattr(response, "output", [])
            for item in output:
                for content in getattr(item, "content", []):
                    if getattr(content, "type", None) == "text":
                        parts.append(getattr(content, "text", ""))
            output_text = "".join(parts)
        usage = getattr(response, "usage", None)
        input_tokens = 0
        output_tokens = 0
        if usage:
            input_tokens = getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)) or 0
            output_tokens = getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)) or 0
        self._record_usage("openai", input_tokens=input_tokens, output_tokens=output_tokens)
        return (output_text or text).strip()

    def _compose_prompts(
        self,
        text: str,
        target_language: str,
        source_language: str | None,
        context: TranslationContext | None,
    ) -> tuple[str, str]:
        context = context or TranslationContext()

        system_parts = [
            "You are a professional subtitle translator.",
            "Translate the subtitle while preserving intent, register, speaker style, and timing cues.",
            "Keep line length natural for subtitles and retain key punctuation unless the language requires changes.",
            "Only translate the text labelled 'Current subtitle'. Do not repeat or paraphrase the previous or next subtitles in your answer.",
        ]
        if source_language and source_language != "und":
            system_parts.append(f"The detected source language is {source_language}.")
        if context.title:
            system_parts.append(
                f"The video title is \"{context.title}\"; use it to resolve proper nouns and domain references."
            )
        if context.previous_text or context.next_text:
            system_parts.append(
                "You may reference the surrounding subtitles to resolve terminology, but never include them in the output."
            )
        system_parts.append(
            "Do not invent new facts; reply with only the translated current subtitle text as a single line."
        )

        system_prompt = " ".join(system_parts)

        user_lines = [f"Target language: {target_language}"]
        if context.segment_index is not None and context.total_segments:
            user_lines.append(
                f"Current segment index: {context.segment_index + 1} of {context.total_segments}."
            )
        if context.previous_text:
            user_lines.append(
                f"Previous subtitle (context only, do not translate): {context.previous_text}"
            )
        user_lines.append(f"Current subtitle (translate this only): {text}")
        if context.next_text:
            user_lines.append(
                f"Next subtitle (context only, do not translate): {context.next_text}"
            )
        user_lines.append(
            "Produce a fluent translation for the current subtitle only. Do not add extra sentences or repeat neighbouring subtitles."
        )

        user_prompt = "\n".join(user_lines)
        return system_prompt, user_prompt

    async def _translate_with_deepseek(
        self,
        text: str,
        target_language: str,
        source_language: str | None,
        context: TranslationContext | None,
    ) -> str:
        url = str(self.settings.deepseek_endpoint)
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        system_prompt, user_prompt = self._compose_prompts(
            text, target_language, source_language, context
        )

        payload = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            response = await self.http.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.RequestError):
            self._record_usage("deepseek")
            return text

        data = response.json()
        choices = data.get("choices", [])
        usage = data.get("usage") or {}
        input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
        self._record_usage("deepseek", input_tokens=input_tokens, output_tokens=output_tokens)
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "").strip()

    async def _translate_with_grok(
        self,
        text: str,
        target_language: str,
        source_language: str | None,
        context: TranslationContext | None,
    ) -> str:
        url = str(self.settings.grok_endpoint)
        headers = {"Authorization": f"Bearer {self.settings.grok_api_key}"}
        system_prompt, user_prompt = self._compose_prompts(
            text, target_language, source_language, context
        )

        payload = {
            "model": self.settings.grok_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            response = await self.http.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError:
            self._record_usage("grok")
            return text

        data = response.json()
        choices = data.get("choices", [])
        usage = data.get("usage") or {}
        input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
        self._record_usage("grok", input_tokens=input_tokens, output_tokens=output_tokens)
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "").strip()

    def _record_usage(self, provider: str, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self._append_usage(self._usage_totals, provider, input_tokens, output_tokens)
        if self._session_usage is not None:
            self._append_usage(self._session_usage, provider, input_tokens, output_tokens)

    @staticmethod
    def _append_usage(container: Dict[str, Dict[str, int]], provider: str, input_tokens: int, output_tokens: int) -> None:
        bucket = container.setdefault(provider, {"requests": 0, "input_tokens": 0, "output_tokens": 0})
        bucket["requests"] += 1
        bucket["input_tokens"] += max(0, input_tokens)
        bucket["output_tokens"] += max(0, output_tokens)

    async def aclose(self) -> None:
        await self.http.aclose()
        if self._openai_client:
            await self._openai_client.close()

    async def __aenter__(self) -> "TranslatorClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()
