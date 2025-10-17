import { type ReactElement, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import clsx from 'clsx';
import './App.css';

interface TokenDetail {
  surface: string;
  reading?: string | null;
  romaji?: string | null;
}

interface Segment {
  start: number;
  end: number;
  text: string;
  tokens?: TokenDetail[] | null;
}

interface DownloadEntry {
  name: string;
  url: string;
}

interface ApiResponse {
  jobId: string;
  videoUrl: string | null;
  language: string;
  segments: Segment[];
  translationLanguage?: string | null;
  translatedSegments?: Segment[] | null;
  downloads?: Record<string, DownloadEntry>;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const languageOptions: { label: string; value: string }[] = [
  { label: '不翻译', value: '' },
  { label: '中文 (zh)', value: 'zh' },
  { label: 'English (en)', value: 'en' },
  { label: '日本語 (ja)', value: 'ja' },
];

function formatTimestamp(value: number): string {
  const minutes = Math.floor(value / 60)
    .toString()
    .padStart(2, '0');
  const seconds = Math.floor(value % 60)
    .toString()
    .padStart(2, '0');
  return `${minutes}:${seconds}`;
}

function App(): ReactElement {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState<string>('zh');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [translationLanguage, setTranslationLanguage] = useState<string | null>(null);
  const [translatedSegments, setTranslatedSegments] = useState<Segment[]>([]);
  const [downloads, setDownloads] = useState<Record<string, DownloadEntry>>({});
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const objectUrlRef = useRef<string | null>(null);
  const [currentHash, setCurrentHash] = useState<string | null>(null);
  const [fetchingCached, setFetchingCached] = useState(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleTimeUpdate = () => {
      const current = video.currentTime;
      const index = segments.findIndex((segment) => current >= segment.start && current < segment.end);
      setActiveIndex(index);
    };

    video.addEventListener('timeupdate', handleTimeUpdate);
    return () => {
      video.removeEventListener('timeupdate', handleTimeUpdate);
    };
  }, [segments]);

  useEffect(() => {
    if (activeIndex < 0) return;
    const container = listRef.current;
    const element = container?.querySelector<HTMLDivElement>(`[data-index="${activeIndex}"]`);
    if (!container || !element) return;

    const containerRect = container.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();
    const offsetWithinContainer = elementRect.top - containerRect.top;
    const desiredPadding = container.clientHeight * 0.3;
    const targetScroll =
      container.scrollTop + offsetWithinContainer - desiredPadding;

    const maxScroll = container.scrollHeight - container.clientHeight;
    const clampedScroll = Math.min(Math.max(targetScroll, 0), Math.max(maxScroll, 0));

    container.scrollTo({ top: clampedScroll, behavior: 'smooth' });
  }, [activeIndex]);

  const pairedSegments = useMemo(() => {
    if (!translatedSegments.length) {
      return segments.map((segment, index) => ({ segment, translation: null, index }));
    }
    return segments.map((segment, index) => ({
      segment,
      translation: translatedSegments[index] ?? null,
      index,
    }));
  }, [segments, translatedSegments]);

  const translationLabel = useMemo(() => {
    if (!translationLanguage) {
      return null;
    }
    return languageOptions.find((option) => option.value === translationLanguage)?.label ?? translationLanguage;
  }, [translationLanguage]);

  const renderTokens = (tokens?: TokenDetail[] | null, fallback?: string) => {
    if (!tokens || tokens.length === 0) {
      return <p className="subtitle-item__text">{fallback}</p>;
    }

    return (
      <div className="subtitle-item__tokens">
        {tokens.map((token, idx) => (
          <span className="subtitle-token" key={`${token.surface}-${idx}`}>
            <span className="subtitle-token__surface">{token.surface}</span>
            {token.romaji ? (
              <span className="subtitle-token__romaji">{token.romaji}</span>
            ) : token.reading ? (
              <span className="subtitle-token__romaji">{token.reading}</span>
            ) : null}
          </span>
        ))}
      </div>
    );
  };
  const computeFileHash = async (inputFile: File): Promise<string> => {
    const buffer = await inputFile.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((byte) => byte.toString(16).padStart(2, '0')).join('');
  };

  const applyApiResponse = (data: ApiResponse) => {
    setSegments(data.segments ?? []);
    setTranslationLanguage(data.translationLanguage ?? null);
    setTranslatedSegments(data.translatedSegments ?? []);
    const mappedDownloads = Object.fromEntries(
      Object.entries(data.downloads ?? {})
        .filter(([, entry]) => Boolean(entry.url))
        .map(([key, entry]) => [key, { name: entry.name, url: `${API_BASE}${entry.url}` }]),
    );
    setDownloads(mappedDownloads);
    setActiveIndex(-1);
  };

  const fetchCachedSubtitles = async (hash: string, targetLang: string, allowFallback = true) => {
    setFetchingCached(true);
    try {
      const { data } = await axios.get<ApiResponse>(`${API_BASE}/api/subtitles/${hash}`, {
        params: { target: targetLang },
      });
      applyApiResponse(data);
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 404) {
        if (targetLang && allowFallback) {
          await fetchCachedSubtitles(hash, '', false);
        } else {
          setSegments([]);
          setTranslationLanguage(null);
          setTranslatedSegments([]);
          setDownloads({});
          setActiveIndex(-1);
        }
      } else {
        console.error(err);
      }
    } finally {
      setFetchingCached(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      setError('请先选择文件');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      let hash = currentHash;
      if (!hash) {
        hash = await computeFileHash(file);
        setCurrentHash(hash);
      }

      const formData = new FormData();
      formData.append('file', file);
      formData.append('target_language', language);
      formData.append('force_refresh', '1');

      const { data } = await axios.post<ApiResponse>(`${API_BASE}/api/transcribe`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      applyApiResponse(data);
    } catch (err) {
      console.error(err);
      setError('生成字幕时出现问题，请检查日志。');
    } finally {
      setLoading(false);
    }
  };

  const handleSubtitleClick = (index: number) => {
    const video = videoRef.current;
    if (!video) return;
    const target = segments[index];
    video.currentTime = Math.max(0, target.start - 0.05);
    video.play().catch(() => undefined);
  };

  const handleFileChange = async (selectedFile: File | null) => {
    setFile(selectedFile);

    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }

    if (selectedFile) {
      const objectUrl = URL.createObjectURL(selectedFile);
      objectUrlRef.current = objectUrl;
      setVideoSrc(objectUrl);
      setSegments([]);
      setTranslatedSegments([]);
      setDownloads({});
      setTranslationLanguage(null);
      setActiveIndex(-1);

      try {
        const hash = await computeFileHash(selectedFile);
        setCurrentHash(hash);
      } catch (hashError) {
        console.error('Failed to compute file hash', hashError);
        setCurrentHash(null);
      }
    } else {
      setVideoSrc(null);
      setSegments([]);
      setTranslatedSegments([]);
      setDownloads({});
      setTranslationLanguage(null);
      setActiveIndex(-1);
      setCurrentHash(null);
    }
  };

  useEffect(() => () => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!currentHash) {
      return;
    }
    fetchCachedSubtitles(currentHash, language).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentHash, language]);

  return (
    <div className="app">
      <header className="app__header">
        <h1>LingoView — 字幕生成与翻译</h1>
        <form onSubmit={handleSubmit} className="upload-form upload-form--inline">
          <label className="upload-form__field upload-form__field--inline">
            <span>选择文件</span>
            <input
              type="file"
              accept="video/*,audio/*,video/x-matroska,video/mpeg,.mkv,.mpv"
              onChange={(event) => {
                void handleFileChange(event.target.files?.[0] ?? null);
              }}
            />
          </label>

          <label className="upload-form__field upload-form__field--inline">
            <span>翻译目标语言</span>
            <select value={language} onChange={(event) => setLanguage(event.target.value)}>
              {languageOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <button
            className="upload-form__submit upload-form__submit--inline"
            type="submit"
            disabled={loading || fetchingCached}
          >
            {loading ? '处理中…' : fetchingCached ? '加载中…' : '生成字幕'}
          </button>

          {error && <p className="upload-form__error">{error}</p>}
        </form>
      </header>

      <div className="app__content">
        <section className="app__player-section">
          {videoSrc ? (
            <video ref={videoRef} className="video-player" controls src={videoSrc} />
          ) : (
            <p className="video-placeholder">请选择文件并生成字幕后开始播放</p>
          )}

          <div className="subtitle-list" ref={listRef}>
            {pairedSegments.map(({ segment, translation, index }) => (
              <div
                key={index}
                data-index={index}
                className={clsx('subtitle-item', { 'subtitle-item--active': index === activeIndex })}
              >
                <button type="button" onClick={() => handleSubtitleClick(index)}>
                  {formatTimestamp(segment.start)} → {formatTimestamp(segment.end)}
                </button>
                {renderTokens(segment.tokens, segment.text)}
                {translation && (
                  <div className="subtitle-item__translation">
                    {translationLabel ? <span className="subtitle-translation__label">{translationLabel}</span> : null}
                    {renderTokens(translation.tokens, translation.text)}
                  </div>
                )}
              </div>
            ))}
            {!pairedSegments.length && !loading && <p>尚未生成字幕。</p>}
          </div>

          {downloads && Object.keys(downloads).length > 0 && (
            <div className="downloads downloads--inline">
              <h2>导出文件</h2>
              <ul>
                {Object.entries(downloads).map(([key, entry]) => (
                  <li key={key}>
                    <a href={entry.url} download>
                      {entry.name}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <aside className="app__dictionary-panel">
          <h2>词语释义</h2>
          <p>后续在此展示点击词语的词典解释与例句。</p>
        </aside>
      </div>
    </div>
  );
}

export default App;
