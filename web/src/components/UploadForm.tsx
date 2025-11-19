import { type ReactElement } from 'react';

interface UploadFormProps {
    handleSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
    loading: boolean;
    fetchingCached: boolean;
    error: string | null;
    language: string;
    setLanguage: (lang: string) => void;
    handleFileChange: (file: File | null) => void;
}

const languageOptions: { label: string; value: string }[] = [
    { label: '不翻译', value: '' },
    { label: '中文 (zh)', value: 'zh' },
    { label: 'English (en)', value: 'en' },
    { label: '日本語 (ja)', value: 'ja' },
];

export function UploadForm({
    handleSubmit,
    loading,
    fetchingCached,
    error,
    language,
    setLanguage,
    handleFileChange,
}: UploadFormProps): ReactElement {
    return (
        <form onSubmit={handleSubmit} className="upload-form upload-form--inline">
            <label className="upload-form__field upload-form__field--inline">
                <span>选择文件</span>
                <input
                    type="file"
                    accept="video/*,audio/*,video/x-matroska,video/mpeg,.mkv,.mpv"
                    onChange={(event) => {
                        handleFileChange(event.target.files?.[0] ?? null);
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
    );
}
