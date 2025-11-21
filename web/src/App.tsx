import { type ReactElement, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import './App.css';
import { DictionaryPanel } from './components/DictionaryPanel';
import { SubtitleList } from './components/SubtitleList';
import { UploadForm } from './components/UploadForm';
import { VideoPlayer } from './components/VideoPlayer';
import { type ApiResponse, type DictionaryResult, type DownloadEntry, type Segment } from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const languageOptions: { label: string; value: string }[] = [
  { label: '不翻译', value: '' },
  { label: '中文 (zh)', value: 'zh' },
  { label: 'English (en)', value: 'en' },
  { label: '日本語 (ja)', value: 'ja' },
];

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

  // Dictionary State
  const [dictionaryData, setDictionaryData] = useState<DictionaryResult | null>(null);
  const [dictionaryLoading, setDictionaryLoading] = useState(false);
  const [dictionaryError, setDictionaryError] = useState<string | null>(null);

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

    if (data.videoUrl) {
      setVideoSrc(`${API_BASE}${data.videoUrl}`);
      // Revoke old object URL to free memory
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    }

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

  const handleTokenClick = async (token: string, context: string) => {
    setDictionaryLoading(true);
    setDictionaryError(null);
    setDictionaryData(null);

    try {
      const { data } = await axios.post<DictionaryResult>(`${API_BASE}/api/dictionary/lookup`, {
        word: token,
        context: context,
        target_lang: 'zh', // Default to Chinese explanation
      });
      setDictionaryData(data);
    } catch (err) {
      console.error(err);
      setDictionaryError('查询失败，请稍后再试。');
    } finally {
      setDictionaryLoading(false);
    }
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
        <UploadForm
          handleSubmit={handleSubmit}
          loading={loading}
          fetchingCached={fetchingCached}
          error={error}
          language={language}
          setLanguage={setLanguage}
          handleFileChange={handleFileChange}
        />
      </header>

      <div className="app__content">
        <div className="app__main-column">
          <VideoPlayer videoRef={videoRef} videoSrc={videoSrc} />

          <DictionaryPanel
            data={dictionaryData}
            loading={dictionaryLoading}
            error={dictionaryError}
          />

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
        </div>

        <div className="app__side-column">
          <SubtitleList
            pairedSegments={pairedSegments}
            activeIndex={activeIndex}
            handleSubtitleClick={handleSubtitleClick}
            listRef={listRef}
            translationLabel={translationLabel}
            loading={loading}
            onTokenClick={handleTokenClick}
          />
        </div>
      </div>
    </div>
  );
}

export default App;

