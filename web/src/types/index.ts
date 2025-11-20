export interface TokenDetail {
    surface: string;
    reading?: string | null;
    romaji?: string | null;
}

export interface Segment {
    start: number;
    end: number;
    text: string;
    tokens?: TokenDetail[] | null;
}

export interface DownloadEntry {
    name: string;
    url: string;
}

export interface DictionaryResult {
    word: string;
    definition: string;
    part_of_speech?: string | null;
    pronunciation?: string | null;
    example?: string | null;
}

export interface ApiResponse {
    jobId: string;
    videoUrl: string | null;
    language: string;
    segments: Segment[];
    translationLanguage?: string | null;
    translatedSegments?: Segment[] | null;
    downloads?: Record<string, DownloadEntry>;
}

export interface PairedSegment {
    segment: Segment;
    translation: Segment | null;
    index: number;
}
