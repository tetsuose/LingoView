from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from .config import load_settings
from .formats import build_json, build_srt
from .exports import prepare_and_save_exports
from .pipeline import SubtitlePipeline, SubtitleResult


def _segments_to_dataframe(segments):
    if not segments:
        return pd.DataFrame(columns=["start", "end", "text", "tokens"])
    return pd.DataFrame(
        [
            {
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "text": segment.text,
                "tokens": " ".join(segment.tokens or []),
            }
            for segment in segments
        ]
    )


def _load_media_bytes(path: Path) -> tuple[bytes, Optional[str]]:
    cache_key = "_lingoview_media_bytes"
    cached = st.session_state.get(cache_key)
    if cached and cached[0] == str(path.resolve()):
        return cached[1], cached[2]
    data = path.read_bytes()
    suffix = path.suffix.lower().lstrip(".")
    return data, suffix


def _render_media_with_subtitles(result: SubtitleResult) -> None:
    media_data = st.session_state.get("_lingoview_media_bytes")
    if not media_data:
        st.warning("未缓存媒体文件，无法展示播放器。")
        return

    _, media_bytes, suffix = media_data
    mime = f"video/{suffix or 'mp4'}"
    seek_to = st.session_state.get("_lingoview_seek", 0.0)

    col_video, col_table = st.columns([2, 3])
    with col_video:
        st.subheader("播放器")
        st.video(media_bytes, format=mime, start_time=int(seek_to))

    with col_table:
        st.subheader("字幕列表")
        translation_segments = result.translated_segments or []
        for index, segment in enumerate(result.segments):
            label = f"{segment.start:6.2f}s → {segment.end:6.2f}s"
            if st.button(label, key=f"seek-{index}"):
                st.session_state["_lingoview_seek"] = segment.start
                st.rerun()
            st.markdown(f"**原文：** {segment.text}")
            if index < len(translation_segments):
                st.markdown(f"*译文：* {translation_segments[index].text}")
            st.divider()
        if not result.segments:
            st.info("未检测到字幕片段")


def _display_result(result: SubtitleResult, exports: dict[str, dict[str, str | Path]]) -> None:
    _render_media_with_subtitles(result)

    info_lines: list[str] = []

    srt_original = (
        exports.get("srt_original", {}).get("content")
        if isinstance(exports.get("srt_original", {}).get("content"), str)
        else build_srt(result.segments)
    )
    st.download_button(
        label="下载原始字幕 SRT",
        data=srt_original,
        file_name="lingoview_original.srt",
        mime="text/plain",
    )
    if "srt_original" in exports:
        info_lines.append(Path(exports["srt_original"]["path"]).name)

    if result.translated_segments:
        srt_translated = (
            exports.get("srt_translation", {}).get("content")
            if isinstance(exports.get("srt_translation", {}).get("content"), str)
            else build_srt(result.translated_segments)
        )
        st.download_button(
            label="下载翻译字幕 SRT",
            data=srt_translated,
            file_name="lingoview_translation.srt",
            mime="text/plain",
        )
        if "srt_translation" in exports:
            info_lines.append(Path(exports["srt_translation"]["path"]).name)

    json_original = (
        exports.get("json_original", {}).get("content")
        if isinstance(exports.get("json_original", {}).get("content"), str)
        else build_json(result, use_translation=False)
    )
    st.download_button(
        label="下载 JSON (原文)",
        data=json_original,
        file_name="lingoview_original.json",
        mime="application/json",
    )
    if "json_original" in exports:
        info_lines.append(Path(exports["json_original"]["path"]).name)

    if result.translated_segments:
        json_translation = (
            exports.get("json_translation", {}).get("content")
            if isinstance(exports.get("json_translation", {}).get("content"), str)
            else build_json(result, use_translation=True)
        )
        st.download_button(
            label="下载 JSON (翻译)",
            data=json_translation,
            file_name="lingoview_translation.json",
            mime="application/json",
        )
        if "json_translation" in exports:
            info_lines.append(Path(exports["json_translation"]["path"]).name)

    if exports:
        export_dir = Path(next(iter(exports.values()))["path"]).parent
        if info_lines:
            st.info(f"字幕已保存至 {export_dir}\n" + "\n".join(info_lines))


def main() -> None:
    st.set_page_config(page_title="LingoView Web UI", layout="wide")
    st.title("LingoView — 字幕生成与翻译")

    settings = load_settings()
    st.sidebar.header("设置")
    st.sidebar.code(
        f"Whisper model: {settings.whisper_model}\n"
        f"Grok model: {settings.grok_model}\n"
        f"Chunks dir: {settings.storage_dir}",
        language="bash",
    )

    default_media = settings.storage_dir / "last_media.txt"
    default_media_path = ""
    if default_media.exists():
        try:
            default_media_path = default_media.read_text(encoding="utf-8").strip()
        except OSError:
            default_media_path = ""

    media_path = st.text_input("输入媒体文件路径", value=default_media_path, help="输入本地音频或视频的绝对路径")
    uploaded_file = st.file_uploader(
        "或选择本地文件",
        type=["mp4", "mkv", "mov", "mpv", "mp3", "wav", "m4a"],
        accept_multiple_files=False,
    )
    if uploaded_file is not None:
        temp_path = settings.storage_dir / f"uploaded-{uploaded_file.name}"
        with temp_path.open("wb") as buffer:
            buffer.write(uploaded_file.read())
        media_path = str(temp_path)

    language_options = {
        "不翻译": "",
        "中文 (zh)": "zh",
        "English (en)": "en",
        "日本語 (ja)": "ja",
    }
    translate_label = st.selectbox("翻译目标语言", options=list(language_options.keys()), index=1)
    translate_to = language_options[translate_label]

    run_button = st.button("生成字幕", key="run", type="primary")

    if run_button:
        if not media_path:
            st.error("请先输入媒体文件路径")
            return
        path = Path(media_path).expanduser()
        if not path.exists():
            st.error("文件不存在，请检查路径")
            return

        try:
            default_media.write_text(str(path), encoding="utf-8")
        except OSError:
            pass

        with st.spinner("处理中，请稍候…"):
            pipeline = SubtitlePipeline(settings)
            try:
                result = asyncio.run(
                    pipeline.generate(
                        path,
                        translate_to or None,
                        media_title=path.stem,
                    )
                )
            except Exception as error:  # pragma: no cover - runtime errors
                st.error(f"处理失败：{error}")
                return

        abs_path = path.resolve()
        media_bytes, media_suffix = _load_media_bytes(abs_path)
        st.session_state["_lingoview_media_bytes"] = (str(abs_path), media_bytes, media_suffix)
        st.session_state["_lingoview_seek"] = 0.0
        st.session_state["_lingoview_result"] = result
        exports = prepare_and_save_exports(result, abs_path, settings)
        st.session_state["_lingoview_exports"] = exports

        st.success("字幕生成完成")
        _display_result(result, exports)
    else:
        cached_result = st.session_state.get("_lingoview_result")
        if cached_result:
            exports = st.session_state.get("_lingoview_exports", {})
            _display_result(cached_result, exports)


if __name__ == "__main__":
    main()
