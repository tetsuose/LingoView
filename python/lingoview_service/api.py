from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import load_settings
from .dictionary import DictionaryResult, lookup_word_in_context
from .exports import compute_source_hash, find_cached_result, prepare_and_save_exports
from .pipeline import SubtitlePipeline
from .tokenizer import get_tokenizer

settings = load_settings()
app = FastAPI()

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DictionaryRequest(BaseModel):
    word: str
    context: str
    source_lang: str = "auto"
    target_lang: str = "zh"


@app.post("/api/dictionary/lookup", response_model=DictionaryResult)
async def lookup_dictionary(request: DictionaryRequest):
    return await lookup_word_in_context(
        word=request.word,
        context=request.context,
        source_lang=request.source_lang,
        target_lang=request.target_lang,
    )


exports_dir = settings.storage_dir / "exports"
exports_dir.mkdir(parents=True, exist_ok=True)

app.mount("/exports", StaticFiles(directory=exports_dir), name="exports")


@app.get("/api/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}


def _build_cached_response(data: dict, job_id: Optional[str] = None) -> dict:
    return {
        "jobId": job_id,
        "videoUrl": None,
        "language": data.get("language"),
        "segments": data.get("segments", []),
        "translationLanguage": data.get("translationLanguage"),
        "translatedSegments": data.get("translatedSegments", []),
        "downloads": {
            key: {
                "name": entry.get("name"),
                "url": f"/exports/{entry.get('name')}"
                if entry.get("name")
                else None,
            }
            for key, entry in data.get("exports", {}).items()
        },
    }


@app.get("/api/subtitles/{source_hash}")
async def get_cached_subtitles(source_hash: str, target: str = "") -> JSONResponse:
    cached = find_cached_result(settings, source_hash, target or None)
    if not cached:
        raise HTTPException(status_code=404, detail="Subtitle not found")
    cached_data, _path = cached
    response = _build_cached_response(cached_data, job_id=f"cache-{source_hash[:10]}")
    return JSONResponse(response)


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    target_language: str = Form(""),
    force_refresh: bool = Form(False),
) -> JSONResponse:
    suffix = Path(file.filename).suffix or ".mp4"
    job_id = uuid.uuid4().hex
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        with temp_file as destination:
            while chunk := file.file.read(1024 * 1024):
                destination.write(chunk)

        media_path = Path(temp_file.name)
        source_hash = compute_source_hash(media_path)
        cached = find_cached_result(settings, source_hash, target_language or None)

        if cached and not force_refresh:
            cached_data, _metadata_path = cached
            response = _build_cached_response(cached_data, job_id=job_id)
            return JSONResponse(response)

        media_title = Path(file.filename).stem if file.filename else None
        pipeline = SubtitlePipeline(settings=settings)
        try:
            result = await pipeline.generate(
                media_path,
                target_language or None,
                media_title=media_title,
            )
        except Exception as exc:  # pragma: no cover - runtime errors
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        export_map = prepare_and_save_exports(
            result,
            settings=settings,
            source_hash=source_hash,
            original_name=file.filename or "upload",
        )
    finally:
        try:
            Path(temp_file.name).unlink(missing_ok=True)
        except OSError:
            pass

    response = {
        "jobId": job_id,
        "videoUrl": None,
        "language": result.language,
        "segments": [
            {
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
            for segment in result.segments
        ],
        "translationLanguage": result.translation_language,
        "translatedSegments": [
            {
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
            for segment in (result.translated_segments or [])
        ],
        "downloads": {
            key: {
                "name": Path(value["path"]).name,
                "url": f"/exports/{Path(value['path']).name}",
            }
            for key, value in export_map.items()
        },
    }

    return JSONResponse(response)


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run("lingoview_service.api:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":  # pragma: no cover
    main()
