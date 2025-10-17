from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import load_settings
from .formats import build_json, build_srt, write_text
from .pipeline import SubtitlePipeline

app = typer.Typer(add_completion=False, help="LingoView transcription & translation CLI")
console = Console()


@app.command()
def transcribe(
    media: Path = typer.Argument(..., exists=True, readable=True, help="Input audio/video file"),
    translate_to: Optional[str] = typer.Option(None, "--translate", "-t", help="Target language code"),
    tokens: bool = typer.Option(True, help="Include tokenizer output in table"),
    json_output: Optional[Path] = typer.Option(None, help="Write JSON subtitles to the given path"),
    srt_output: Optional[Path] = typer.Option(None, help="Write SRT subtitles to the given path"),
    srt_source: str = typer.Option(
        "original",
        help="Source for SRT export: 'original' or 'translation'",
        show_default=True,
    ),
):
    """Transcribe a media file using the local faster-whisper pipeline and optional translation."""

    settings = load_settings()
    pipeline = SubtitlePipeline(settings)
    result = asyncio.run(
        pipeline.generate(media, translate_to, media_title=media.stem)
    )

    table = Table(title=f"Subtitle segments ({result.language})")
    table.add_column("Start", style="cyan")
    table.add_column("End", style="cyan")
    table.add_column("Text", overflow="fold")
    if tokens:
        table.add_column("Tokens", overflow="fold")

    for segment in result.segments:
        row = [f"{segment.start:.2f}", f"{segment.end:.2f}", segment.text]
        if tokens:
            row.append(" ".join(token.surface for token in (segment.tokens or [])))
        table.add_row(*row)
    console.print(table)

    if result.translated_segments:
        t_table = Table(title=f"Translated segments ({translate_to})")
        t_table.add_column("Start", style="magenta")
        t_table.add_column("End", style="magenta")
        t_table.add_column("Text", overflow="fold")
        if tokens:
            t_table.add_column("Tokens", overflow="fold")
        for segment in result.translated_segments:
            row = [f"{segment.start:.2f}", f"{segment.end:.2f}", segment.text]
            if tokens:
                row.append(" ".join(token.surface for token in (segment.tokens or [])))
            t_table.add_row(*row)
        console.print(t_table)

    if json_output:
        selected = srt_source.lower() == "translation"
        payload = build_json(result, use_translation=selected)
        write_text(json_output, payload)
        console.log(f"[green]JSON written to[/green] {json_output}")

    if srt_output:
        use_translation = srt_source.lower() == "translation"
        if use_translation and not result.translated_segments:
            console.log("[yellow]No translated segments available; falling back to original text[/yellow]")
            use_translation = False
        segments = result.translated_segments if use_translation else result.segments
        srt_content = build_srt(segments or [])
        write_text(srt_output, srt_content)
        console.log(f"[green]SRT written to[/green] {srt_output}")


@app.command()
def settings() -> None:
    """Print currently resolved settings (safe subset)."""

    cfg = load_settings()
    safe = {
        "whisper_model": cfg.whisper_model,
        "grok_model": cfg.grok_model,
        "storage_dir": str(cfg.storage_dir),
        "max_parallel_requests": cfg.max_parallel_requests,
        "chunk_seconds": cfg.chunk_seconds,
        "chunk_overlap": cfg.chunk_overlap,
        "tokenizer_backend": cfg.tokenizer_backend,
        "sudachi_mode": cfg.sudachi_mode,
    }
    console.print(safe)


if __name__ == "__main__":  # pragma: no cover
    app()
