from __future__ import annotations

import asyncio

from lingoview_service.config import ServiceSettings
from lingoview_service.translate import TranslatorClient


class DummyTranslatorClient(TranslatorClient):
    def __init__(self, settings: ServiceSettings) -> None:
        super().__init__(settings)
        self.calls: list[str] = []

    async def _translate_with_grok(self, *args, **kwargs) -> str:  # type: ignore[override]
        self.calls.append("grok")
        return "grok"

    async def _translate_with_deepseek(self, *args, **kwargs) -> str:  # type: ignore[override]
        self.calls.append("deepseek")
        return "deepseek"


async def _translate(client: DummyTranslatorClient) -> str:
    try:
        return await client.translate_text("hello", "zh", "en")
    finally:
        await client.aclose()


def test_translator_prefers_configured_provider_grok():
    settings = ServiceSettings(
        grok_api_key="grok",
        deepseek_api_key="deepseek",
        translator_provider="grok",
        openai_api_key=None,
    )
    client = DummyTranslatorClient(settings)
    result = asyncio.run(_translate(client))

    assert result == "grok"
    assert client.calls[0] == "grok"


def test_translator_auto_falls_back_to_grok_on_failure(monkeypatch):
    settings = ServiceSettings(
        grok_api_key="grok",
        deepseek_api_key="deepseek",
        translator_provider="auto",
        openai_api_key=None,
    )
    client = DummyTranslatorClient(settings)

    async def failing_deepseek(*args, **kwargs):  # type: ignore[override]
        client.calls.append("deepseek")
        raise RuntimeError("deepseek failed")

    monkeypatch.setattr(client, "_translate_with_deepseek", failing_deepseek)

    result = asyncio.run(_translate(client))

    assert result == "grok"
    assert client.calls == ["grok"]
