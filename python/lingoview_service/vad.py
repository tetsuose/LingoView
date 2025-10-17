from __future__ import annotations

import asyncio
import math
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
import soundfile as sf
import webrtcvad

from .config import ServiceSettings

FRAME_DURATION_MS = 30  # 30 ms per frame for WebRTC VAD
MIN_SPEECH_MS = 300
MIN_SILENCE_MS = 450
SPLIT_SILENCE_THRESHOLD_MS = 500
STRONG_SPLIT_SILENCE_MS = 1000
PADDING_MS = 600


@dataclass
class AudioChunk:
    path: Path
    start: float
    end: float
    speech_start: float
    speech_end: float


async def chunk_audio(media_path: Path, settings: ServiceSettings) -> List[AudioChunk]:
    """Chunk audio using WebRTC VAD with overlap and max duration safeguards."""

    return await asyncio.to_thread(_chunk_audio_sync, media_path, settings)


def _chunk_audio_sync(media_path: Path, settings: ServiceSettings) -> List[AudioChunk]:
    storage_dir = settings.storage_dir / "chunks"
    storage_dir.mkdir(parents=True, exist_ok=True)

    normalised_path = storage_dir / f"normalised-{uuid.uuid4().hex}.wav"
    try:
        _convert_to_pcm_wave(media_path, normalised_path)
        data, sample_rate = sf.read(normalised_path)
        if sample_rate != 16000:
            raise RuntimeError("Expected 16kHz sample rate after normalisation")
        if data.ndim > 1:
            data = data[:, 0]

        pcm = np.clip(data, -1.0, 1.0)
        pcm = (pcm * 32768).astype(np.int16)

        frame_size = int(sample_rate * FRAME_DURATION_MS / 1000)
        total_frames = len(pcm) // frame_size
        if total_frames == 0:
            return []

        duration_seconds = len(pcm) / sample_rate

        if not settings.enable_vad:
            chunk_path = storage_dir / "chunk-0000.wav"
            sf.write(chunk_path, pcm.astype(np.float32) / 32768.0, sample_rate, subtype="PCM_16")
            return [
                AudioChunk(
                    path=chunk_path,
                    start=0.0,
                    end=duration_seconds,
                    speech_start=0.0,
                    speech_end=duration_seconds,
                )
            ]

        vad = webrtcvad.Vad(2)
        min_speech_frames = max(1, MIN_SPEECH_MS // FRAME_DURATION_MS)
        min_silence_frames = max(1, MIN_SILENCE_MS // FRAME_DURATION_MS)
        frame_duration_seconds = FRAME_DURATION_MS / 1000.0
        padding_seconds = PADDING_MS / 1000.0
        small_gap_seconds = SPLIT_SILENCE_THRESHOLD_MS / 1000.0
        large_gap_seconds = STRONG_SPLIT_SILENCE_MS / 1000.0
        max_chunk_seconds = max(1.0, float(settings.chunk_seconds))
        overlap_seconds = max(0.0, float(settings.chunk_overlap))
        effective_overlap_seconds = max(overlap_seconds, 0.75)

        speech_segments_frames = _detect_speech_segments(
            pcm, frame_size, vad, total_frames, min_speech_frames, min_silence_frames
        )

        speech_segments_seconds: List[dict[str, float]] = []
        for raw_start, raw_end in speech_segments_frames:
            start_time = raw_start * frame_duration_seconds
            end_time = min(duration_seconds, raw_end * frame_duration_seconds)
            if end_time <= start_time:
                continue
            if not speech_segments_seconds:
                speech_segments_seconds.append(
                    {
                        "speech_start": start_time,
                        "speech_end": end_time,
                    }
                )
                continue

            previous = speech_segments_seconds[-1]
            gap = start_time - previous["speech_end"]
            if gap <= small_gap_seconds:
                previous["speech_end"] = max(previous["speech_end"], end_time)
            else:
                speech_segments_seconds.append(
                    {
                        "speech_start": start_time,
                        "speech_end": end_time,
                    }
                )

        if not speech_segments_seconds:
            speech_segments_seconds = [
                {
                    "speech_start": 0.0,
                    "speech_end": duration_seconds,
                }
            ]

        for segment in speech_segments_seconds:
            segment["chunk_start"] = max(0.0, segment["speech_start"] - padding_seconds)
            segment["chunk_end"] = min(duration_seconds, segment["speech_end"] + padding_seconds)

        for idx in range(len(speech_segments_seconds) - 1):
            current = speech_segments_seconds[idx]
            nxt = speech_segments_seconds[idx + 1]
            gap = nxt["speech_start"] - current["speech_end"]
            if gap <= 0:
                continue
            if gap <= large_gap_seconds:
                split_point = current["speech_end"] + gap / 2.0
                current["chunk_end"] = min(current["chunk_end"], split_point)
                nxt["chunk_start"] = max(nxt["chunk_start"], split_point)

        chunks: List[AudioChunk] = []
        chunk_index = 0

        for segment in speech_segments_seconds:
            chunk_start = segment["chunk_start"]
            chunk_end = segment["chunk_end"]
            speech_start = segment["speech_start"]
            speech_end = segment["speech_end"]

            if chunk_end - chunk_start <= 0:
                continue

            current_start = chunk_start
            while current_start < chunk_end:
                segment_limit = min(chunk_end, current_start + max_chunk_seconds)

                chunk_start_time = max(chunk_start, current_start - effective_overlap_seconds)
                chunk_end_time = min(chunk_end, segment_limit + effective_overlap_seconds)

                start_sample = max(0, int(math.floor(chunk_start_time * sample_rate)))
                end_sample = min(len(pcm), int(math.ceil(chunk_end_time * sample_rate)))
                if end_sample <= start_sample:
                    current_start = segment_limit
                    continue

                chunk_data = pcm[start_sample:end_sample]
                if not len(chunk_data):
                    current_start = segment_limit
                    continue

                real_chunk_start = start_sample / sample_rate
                real_chunk_end = end_sample / sample_rate

                chunk_path = storage_dir / f"chunk-{chunk_index:04d}.wav"
                sf.write(
                    chunk_path,
                    chunk_data.astype(np.float32) / 32768.0,
                    sample_rate,
                    subtype="PCM_16",
                )

                speech_start_time = max(real_chunk_start, speech_start)
                speech_end_time = min(real_chunk_end, speech_end)
                if speech_end_time <= speech_start_time:
                    speech_start_time = real_chunk_start
                    speech_end_time = real_chunk_end

                chunks.append(
                    AudioChunk(
                        path=chunk_path,
                        start=real_chunk_start,
                        end=real_chunk_end,
                        speech_start=speech_start_time,
                        speech_end=speech_end_time,
                    )
                )
                chunk_index += 1
                current_start = segment_limit

        return chunks
    finally:
        if normalised_path.exists():
            try:
                normalised_path.unlink()
            except OSError:
                pass


def _convert_to_pcm_wave(source: Path, target: Path) -> None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        str(target),
    ]
    subprocess.run(cmd, check=True)


def _detect_speech_segments(
    pcm: np.ndarray,
    frame_size: int,
    vad: webrtcvad.Vad,
    total_frames: int,
    min_speech_frames: int,
    min_silence_frames: int,
) -> List[tuple[int, int]]:
    speech_segments: List[tuple[int, int]] = []
    start_frame: int | None = None
    silence_run = 0
    energy_threshold = 400.0
    for frame_index in range(total_frames):
        frame = pcm[frame_index * frame_size : (frame_index + 1) * frame_size]
        abs_mean = float(np.mean(np.abs(frame)))
        is_speech = vad.is_speech(frame.tobytes(), 16000)
        if not is_speech and abs_mean > energy_threshold:
            is_speech = True
        if is_speech:
            silence_run = 0
            if start_frame is None:
                start_frame = frame_index
        else:
            if start_frame is not None:
                silence_run += 1
                if silence_run >= min_silence_frames:
                    end_frame = frame_index - min_silence_frames + 1
                    if end_frame - start_frame >= min_speech_frames:
                        speech_segments.append((start_frame, end_frame))
                    start_frame = None
                    silence_run = 0
            else:
                silence_run = 0

    if start_frame is not None:
        end_frame = total_frames
        if end_frame - start_frame >= min_speech_frames:
            speech_segments.append((start_frame, end_frame))

    return speech_segments

