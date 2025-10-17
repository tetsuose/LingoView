export type DictionaryLanguage = 'en' | 'en-zh' | 'ja' | 'ja-zh' | 'zh';

export interface DictionaryEntry {
  word: string;
  reading?: string;
  pronunciation?: string;
  forms?: string[];
  pos?: string[];
  definitions: string[];
  source?: string;
  metadata?: Record<string, unknown>;
}
