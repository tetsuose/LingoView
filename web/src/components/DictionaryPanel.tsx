import { type ReactElement } from 'react';
import { type DictionaryResult } from '../types';

interface DictionaryPanelProps {
    data: DictionaryResult | null;
    loading: boolean;
    error: string | null;
}

export function DictionaryPanel({ data, loading, error }: DictionaryPanelProps): ReactElement {
    return (
        <aside className="dictionary-panel">
            <h2>词语释义</h2>
            {loading && <p className="dictionary-loading">正在查询…</p>}
            {error && <p className="dictionary-error">{error}</p>}
            {!loading && !error && !data && <p className="dictionary-placeholder">点击字幕中的单词查看解释。</p>}

            {data && (
                <div className="dictionary-result">
                    <div className="dictionary-result__header">
                        <h3 className="dictionary-result__word">{data.word}</h3>
                        {data.pronunciation && <span className="dictionary-result__pronunciation">[{data.pronunciation}]</span>}
                    </div>
                    {data.part_of_speech && <span className="dictionary-result__pos">{data.part_of_speech}</span>}
                    <p className="dictionary-result__definition">{data.definition}</p>
                    {data.example && (
                        <div className="dictionary-result__example">
                            <strong>例句：</strong>
                            <p>{data.example}</p>
                        </div>
                    )}
                </div>
            )}
        </aside>
    );
}
