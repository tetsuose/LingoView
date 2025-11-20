import { type ReactElement, useEffect, type RefObject } from 'react';
import clsx from 'clsx';
import { type PairedSegment, type TokenDetail } from '../types';

interface SubtitleListProps {
    pairedSegments: PairedSegment[];
    activeIndex: number;
    handleSubtitleClick: (index: number) => void;
    listRef: RefObject<HTMLDivElement | null>;
    translationLabel: string | null;
    loading: boolean;
    onTokenClick: (token: string, context: string) => void;
}

function formatTimestamp(value: number): string {
    const minutes = Math.floor(value / 60)
        .toString()
        .padStart(2, '0');
    const seconds = Math.floor(value % 60)
        .toString()
        .padStart(2, '0');
    return `${minutes}:${seconds}`;
}

const renderTokens = (
    tokens: TokenDetail[] | undefined | null,
    fallback: string | undefined,
    context: string,
    onTokenClick: (token: string, context: string) => void,
) => {
    if (!tokens || tokens.length === 0) {
        return <p className="subtitle-item__text">{fallback}</p>;
    }

    return (
        <div className="subtitle-item__tokens">
            {tokens.map((token, idx) => (
                <span
                    className="subtitle-token"
                    key={`${token.surface}-${idx}`}
                    onClick={(e) => {
                        e.stopPropagation();
                        onTokenClick(token.surface, context);
                    }}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.stopPropagation();
                            onTokenClick(token.surface, context);
                        }
                    }}
                >
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

export function SubtitleList({
    pairedSegments,
    activeIndex,
    handleSubtitleClick,
    listRef,
    translationLabel,
    loading,
    onTokenClick,
}: SubtitleListProps): ReactElement {

    useEffect(() => {
        if (activeIndex < 0) return;
        const container = listRef.current;
        const element = container?.querySelector<HTMLDivElement>(`[data-index="${activeIndex}"]`);
        if (!container || !element) return;

        element.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, [activeIndex, listRef]);

    return (
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
                    {renderTokens(segment.tokens, segment.text, segment.text, onTokenClick)}
                    {translation && (
                        <div className="subtitle-item__translation">
                            {translationLabel ? <span className="subtitle-translation__label">{translationLabel}</span> : null}
                            {renderTokens(translation.tokens, translation.text, translation.text, onTokenClick)}
                        </div>
                    )}
                </div>
            ))}
            {!pairedSegments.length && !loading && <p>尚未生成字幕。</p>}
        </div>
    );
}
