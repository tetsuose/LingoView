import { type ReactElement } from 'react';

export function DictionaryPanel(): ReactElement {
    return (
        <aside className="app__dictionary-panel">
            <h2>词语释义</h2>
            <p>后续在此展示点击词语的词典解释与例句。</p>
        </aside>
    );
}
