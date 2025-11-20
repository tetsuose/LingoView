from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from .config import ServiceSettings, load_settings


class DictionaryResult(BaseModel):
    word: str
    definition: str
    part_of_speech: Optional[str] = None
    pronunciation: Optional[str] = None
    example: Optional[str] = None


def _get_cache_path(settings: ServiceSettings) -> Path:
    return settings.storage_dir / "dictionary_cache.json"


def _load_cache(settings: ServiceSettings) -> dict:
    path = _get_cache_path(settings)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_to_cache(settings: ServiceSettings, key: str, result: DictionaryResult) -> None:
    path = _get_cache_path(settings)
    # Reload to minimize race conditions (simple file lock substitute)
    cache = _load_cache(settings)
    cache[key] = result.model_dump()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save dictionary cache: {e}")


async def lookup_word_in_context(
    word: str, context: str, source_lang: str, target_lang: str
) -> DictionaryResult:
    settings = load_settings()

    # 1. Check Cache
    cache_key = hashlib.md5(f"{word}:{context}:{target_lang}".encode("utf-8")).hexdigest()
    cache = _load_cache(settings)
    if cache_key in cache:
        print(f"Dictionary cache hit for: {word}")
        return DictionaryResult(**cache[cache_key])
    
    # Determine provider and config
    api_key = None
    base_url = None
    model = None
    
    provider = settings.translator_provider
    if provider == "auto":
        if settings.openai_api_key:
            provider = "openai"
        elif settings.deepseek_api_key:
            provider = "deepseek"
        elif settings.grok_api_key:
            provider = "grok"
            
    if provider == "deepseek" and settings.deepseek_api_key:
        api_key = settings.deepseek_api_key
        base_url = str(settings.deepseek_endpoint).replace("/chat/completions", "") # OpenAI client appends /chat/completions usually, but base_url should be root. Actually DeepSeek base is https://api.deepseek.com
        base_url = "https://api.deepseek.com"
        model = settings.deepseek_model
    elif provider == "grok" and settings.grok_api_key:
        api_key = settings.grok_api_key
        base_url = "https://api.x.ai/v1"
        model = settings.grok_model
    else: # Default to OpenAI
        api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
        base_url = settings.openai_translate_endpoint or settings.openai_api_base
        model = settings.openai_translate_model

    if not api_key:
        return DictionaryResult(
            word=word,
            definition="API Key not configured for dictionary lookup.",
            example="Please configure OPENAI_API_KEY, DEEPSEEK_API_KEY, or GROK_API_KEY."
        )

    client = AsyncOpenAI(api_key=api_key, base_url=str(base_url) if base_url else None)

    system_prompt = (
        "You are a helpful dictionary assistant. "
        "Your task is to explain the meaning of a specific word found in a sentence. "
        "You must provide the definition that fits the context of the sentence. "
        "Return the result in strict JSON format."
    )

    user_prompt = (
        f"Word: {word}\n"
        f"Context Sentence: {context}\n"
        f"Source Language: {source_lang}\n"
        f"Target Language (for explanation): {target_lang}\n\n"
        "Please provide:\n"
        "1. The definition of the word as used in this context.\n"
        "2. The part of speech (e.g., Noun, Verb).\n"
        "3. The pronunciation (IPA or phonetic) if applicable.\n"
        "4. A short example sentence using the word (different from the context if possible).\n\n"
        "Output JSON format:\n"
        "{\n"
        '  "word": "...",\n'
        '  "definition": "...",\n'
        '  "part_of_speech": "...",\n'
        '  "pronunciation": "...",\n'
        '  "example": "..."\n'
        "}"
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from LLM")

        data = json.loads(content)
        result = DictionaryResult(
            word=data.get("word", word),
            definition=data.get("definition", "No definition found."),
            part_of_speech=data.get("part_of_speech"),
            pronunciation=data.get("pronunciation"),
            example=data.get("example"),
        )
        
        # 2. Save to Cache
        _save_to_cache(settings, cache_key, result)
        
        return result

    except Exception as e:
        print(f"Dictionary lookup failed: {e}")
        return DictionaryResult(
            word=word,
            definition="Failed to retrieve definition.",
            example=str(e)
        )
