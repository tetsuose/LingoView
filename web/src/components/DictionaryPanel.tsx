import { type ReactElement } from 'react';
import { type DictionaryResult } from '../types';

interface DictionaryPanelProps {
    data: DictionaryResult | null;
    loading: boolean;
    error: string | null;
}

export function DictionaryPanel({ data, loading, error }: DictionaryPanelProps): ReactElement {
    return (
        <aside className="app__dictionary-panel">
            <h2>词语释义</h2>
            {loading && <p className="dictionary-loading">正在查询…</p>}
            {error && <p className="dictionary-error">{error}</p>}
            {!loading && !error && !data && <p>点击字幕中的单词查看解释。</p>}

            {data && (
                <div className="dictionary-content">
                    <div className="dictionary-header">
                        <h3 className="dictionary-word">{data.word}</h3>
                        {data.pronunciation && <span className="dictionary-pronunciation">[{data.pronunciation}]</span>}
                    </div>
                    {data.part_of_speech && <span className="dictionary-pos">{data.part_of_speech}</span>}
                    <p className="dictionary-definition">{data.definition}</p>
                    {data.example && (
                        <div className="dictionary-example">
                            <strong>例句：</strong>
                            <p>{data.example}</p>
                        </div>
                    )}
                </div>
            )}
        </aside>
    );
}
