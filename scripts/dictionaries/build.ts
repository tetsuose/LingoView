#!/usr/bin/env tsx
import { createHash } from 'node:crypto';
import { createReadStream, createWriteStream, existsSync } from 'node:fs';
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { createGunzip, createGzip } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline';

import Database from 'better-sqlite3';
import { XMLParser } from 'fast-xml-parser';

import type { DictionaryEntry, DictionaryLanguage } from './types';

type BuildMode = 'sample' | 'production';

interface BuildOptions {
  mode: BuildMode;
  force: boolean;
  rawRoot?: string;
  languages: DictionaryLanguage[];
}

interface ManifestEntry {
  language: DictionaryLanguage;
  entries: number;
  sqlite: string;
  sqliteSha256: string;
  json: string;
  jsonSha256: string;
  source: string;
}

interface KaikkiData {
  source: string;
  enZhEntries: DictionaryEntry[];
  enEntries: DictionaryEntry[];
  translationMap: Map<string, string[]>;
}

interface JmdictData {
  source: string;
  jaZhEntries: DictionaryEntry[];
  jaEntries: DictionaryEntry[];
}

interface CedictData {
  source: string;
  entries: DictionaryEntry[];
  translationMap: Map<string, string[]>;
}

interface BuildContext {
  kaikki?: KaikkiData;
  jmdict?: JmdictData;
  cedict?: CedictData;
}

interface BuilderResult {
  entries: DictionaryEntry[];
  source: string;
}

type Builder = (options: BuildOptions, context: BuildContext) => Promise<BuilderResult | null>;

const DEFAULT_LANGUAGES: DictionaryLanguage[] = ['en-zh', 'ja-zh', 'en', 'ja', 'zh'];

const OUTPUT_DIR = fileURLToPath(new URL('../../resources/dictionaries/', import.meta.url));
const RAW_FALLBACK_DIR = join(OUTPUT_DIR, 'raw');
const MANIFEST_PATH = join(OUTPUT_DIR, 'manifest.json');

const KAIKKI_ARCHIVE = {
  filename: 'kaikki.org-dictionary-English.jsonl.gz',
  url: 'https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl.gz'
};

const JMDICT_ARCHIVE = {
  filename: 'JMdict.gz',
  url: 'http://ftp.edrdg.org/pub/Nihongo/JMdict.gz'
};

const CEDICT_ARCHIVE = {
  filename: 'cedict_1_0_ts_utf-8_mdbg.txt.gz',
  url: 'https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz'
};

const SAMPLE_DICTIONARIES: Partial<Record<DictionaryLanguage, DictionaryEntry[]>> = {
  'en-zh': [
    {
      word: 'hello',
      definitions: ['你好', '您好'],
      forms: ['hello', 'hellos'],
      pos: ['interjection'],
      source: 'Sample (Kaikki Wiktionary)',
      metadata: { frequency: 5 }
    },
    {
      word: 'music',
      definitions: ['音乐', '音乐作品'],
      forms: ['music'],
      pos: ['noun'],
      source: 'Sample (Kaikki Wiktionary)'
    }
  ],
  'ja-zh': [
    {
      word: '勉強',
      reading: 'べんきょう',
      definitions: ['学习', '用功'],
      pos: ['名詞'],
      source: 'Sample (JMdict 中文义)',
      metadata: { jlpt: 'N5' }
    },
    {
      word: 'ありがとう',
      reading: 'ありがとう',
      definitions: ['谢谢', '非常感谢'],
      pos: ['感動詞'],
      source: 'Sample (JMdict 中文义)'
    }
  ],
  en: [
    {
      word: 'study',
      definitions: ['To devote time and attention to acquiring knowledge.', 'To examine closely in order to observe or read.'],
      forms: ['studies', 'studied', 'studying'],
      pos: ['verb', 'noun'],
      source: 'Sample (Kaikki Wiktionary)'
    }
  ],
  ja: [
    {
      word: '学ぶ',
      reading: 'まなぶ',
      definitions: ['to learn', 'to study'],
      pos: ['動詞'],
      source: 'Sample (JMdict)'
    }
  ],
  zh: [
    {
      word: '学习',
      reading: '学习',
      pronunciation: 'xuéxí',
      definitions: ['study; learn'],
      forms: ['學習'],
      pos: ['动词'],
      source: 'Sample (CC-CEDICT stub)',
      metadata: { simplified: '学习', traditional: '學習' }
    }
  ]
};

const STOP_WORDS = new Set(['to', 'the', 'a', 'an', 'of', 'for', 'on', 'in', 'at', 'with', 'and', 'or', 'by', 'be', 'is', 'are']);

const JM_POS_MAP: Record<string, string> = {
  'n': 'noun',
  'adj-i': 'i-adjective',
  'adj-na': 'na-adjective',
  'adj-no': 'no-adjective',
  'adv': 'adverb',
  'vs': 'suru-verb',
  'vt': 'transitive verb',
  'vi': 'intransitive verb',
  'exp': 'expression'
};

const parseArgs = (): BuildOptions => {
  const args = process.argv.slice(2);
  const options: BuildOptions = {
    mode: 'production',
    force: false,
    languages: [...DEFAULT_LANGUAGES]
  };

  args.forEach((arg) => {
    if (arg === '--sample') {
      options.mode = 'sample';
      return;
    }
    if (arg === '--force') {
      options.force = true;
      return;
    }
    if (arg.startsWith('--raw=')) {
      options.rawRoot = arg.substring('--raw='.length);
      return;
    }
    if (arg.startsWith('--languages=')) {
      const raw = arg.substring('--languages='.length);
      const languages = raw.split(',').map((value) => value.trim()).filter(Boolean) as DictionaryLanguage[];
      if (languages.length) {
        options.languages = languages;
      }
    }
  });

  return options;
};

const ensureArray = <T>(value: T | T[] | undefined | null): T[] => {
  if (value === undefined || value === null) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
};

const normalizeEnglishKey = (value: string): string[] => {
  const lowercase = value.toLowerCase();
  const words = lowercase.replace(/[^a-z\s'-]+/g, ' ').trim().replace(/\s+/g, ' ');
  const compact = lowercase.replace(/[^a-z'-]+/g, '');
  const keys = new Set<string>();
  if (words) {
    keys.add(words);
  }
  if (compact) {
    keys.add(compact);
  }
  return Array.from(keys);
};

const normaliseForLanguage = (language: DictionaryLanguage, value: string): string => {
  if (!value) {
    return '';
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return '';
  }
  if (language === 'en' || language === 'en-zh') {
    return trimmed.toLowerCase().replace(/[^a-z\-']+/g, '');
  }
  return trimmed;
};

const toRowPayload = (language: DictionaryLanguage, entry: DictionaryEntry) => {
  const normalized = normaliseForLanguage(language, entry.word);
  const reading = entry.reading ? entry.reading.trim() : null;
  return {
    normalized,
    term: entry.word,
    reading,
    pronunciation: entry.pronunciation ?? null,
    forms: entry.forms?.length ? JSON.stringify(entry.forms) : null,
    pos: entry.pos?.length ? JSON.stringify(entry.pos) : null,
    definitions: JSON.stringify(entry.definitions ?? []),
    source: entry.source ?? null,
    metadata: entry.metadata ? JSON.stringify(entry.metadata) : null
  };
};

const ensureOutputDir = async (): Promise<void> => {
  await mkdir(OUTPUT_DIR, { recursive: true });
};

const ensureRawDir = async (options: BuildOptions): Promise<string> => {
  const target = options.rawRoot ? options.rawRoot : RAW_FALLBACK_DIR;
  await mkdir(target, { recursive: true });
  return target;
};

const checksum = async (filePath: string): Promise<string> => {
  const hash = createHash('sha256');
  const data = await readFile(filePath);
  hash.update(data);
  return hash.digest('hex');
};

const writeGzipJson = async (filePath: string, payload: unknown, force: boolean): Promise<void> => {
  if (existsSync(filePath)) {
    if (!force) {
      throw new Error(`File already exists: ${filePath}. Use --force to overwrite.`);
    }
    await rm(filePath, { force: true });
  }
  const json = JSON.stringify(payload, null, 2);
  const gzip = createGzip({ level: 9 });
  const input = Readable.from(json);
  const output = createWriteStream(filePath);
  await pipeline(input, gzip, output);
};

const writeSqlite = async (
  language: DictionaryLanguage,
  entries: DictionaryEntry[],
  filePath: string,
  force: boolean
): Promise<number> => {
  if (existsSync(filePath)) {
    if (!force) {
      throw new Error(`File already exists: ${filePath}. Use --force to overwrite.`);
    }
    await rm(filePath, { force: true });
  }

  const db = new Database(filePath);
  db.pragma('journal_mode = WAL');
  db.exec(`
    CREATE TABLE IF NOT EXISTS entries (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      normalized TEXT NOT NULL,
      term TEXT NOT NULL,
      reading TEXT,
      pronunciation TEXT,
      forms TEXT,
      pos TEXT,
      definitions TEXT NOT NULL,
      source TEXT,
      metadata TEXT
    );
  `);
  db.exec('CREATE INDEX IF NOT EXISTS idx_entries_normalized ON entries(normalized);');
  db.exec('CREATE INDEX IF NOT EXISTS idx_entries_reading ON entries(reading);');

  const insert = db.prepare(
    `INSERT INTO entries (normalized, term, reading, pronunciation, forms, pos, definitions, source, metadata)
     VALUES (@normalized, @term, @reading, @pronunciation, @forms, @pos, @definitions, @source, @metadata);`
  );

  const payloads = entries
    .map((entry) => toRowPayload(language, entry))
    .filter((row): row is ReturnType<typeof toRowPayload> => Boolean(row.normalized || row.reading));

  const insertMany = db.transaction((rows: ReturnType<typeof toRowPayload>[]) => {
    rows.forEach((row) => {
      insert.run(row);
    });
  });

  try {
    insertMany(payloads);
    db.exec('VACUUM;');
    return payloads.length;
  } finally {
    db.close();
  }
};

const downloadFile = async (url: string, destPath: string, force: boolean): Promise<string> => {
  if (existsSync(destPath)) {
    if (!force) {
      return destPath;
    }
    await rm(destPath, { force: true });
  }

  await mkdir(dirname(destPath), { recursive: true });

  const response = await fetch(url);
  if (!response.ok || !response.body) {
    throw new Error(`Failed to download ${url}: ${response.status} ${response.statusText}`);
  }

  const stream = Readable.fromWeb(response.body as unknown as ReadableStream<Uint8Array>);
  const fileStream = createWriteStream(destPath);
  await pipeline(stream, fileStream);
  return destPath;
};

const readGzipFile = async (filePath: string): Promise<string> => {
  const stream = createReadStream(filePath).pipe(createGunzip());
  const chunks: Buffer[] = [];
  stream.on('data', (chunk) => {
    chunks.push(chunk);
  });
  await new Promise<void>((resolve, reject) => {
    stream.on('end', () => resolve());
    stream.on('error', (error) => reject(error));
  });
  return Buffer.concat(chunks).toString('utf-8');
};

const splitChineseVariants = (value: string): string[] => {
  if (!value) {
    return [];
  }
  return value
    .split(/\s*[\/／、；;]\s*/)
    .map((item) => item.trim())
    .filter(Boolean);
};

const containsHan = (value: string | undefined): boolean => {
  if (!value) {
    return false;
  }
  return /[\p{Script=Han}]/u.test(value);
};

const collectGlosses = (senses: any[] | undefined): string[] => {
  const results: string[] = [];
  ensureArray(senses).forEach((sense) => {
    ensureArray(sense.glosses ?? sense.raw_glosses ?? []).forEach((gloss: unknown) => {
      if (typeof gloss === 'string') {
        const trimmed = gloss.trim();
        if (trimmed) {
          results.push(trimmed);
        }
      }
    });
  });
  return results;
};

const collectPronunciations = (sounds: any[] | undefined): string | undefined => {
  const pronunciations = new Set<string>();
  ensureArray(sounds).forEach((sound) => {
    if (sound && typeof sound.ipa === 'string') {
      const trimmed = sound.ipa.trim();
      if (trimmed) {
        pronunciations.add(trimmed);
      }
    }
  });
  if (!pronunciations.size) {
    return undefined;
  }
  return Array.from(pronunciations).join(', ');
};

const parseKaikki = async (archivePath: string): Promise<KaikkiData> => {
  const enZhEntries: DictionaryEntry[] = [];
  const enEntries: DictionaryEntry[] = [];
  const translationMap = new Map<string, string[]>();
  const source = 'Kaikki (Wiktionary, English edition)';

  const stream = createReadStream(archivePath).pipe(createGunzip());
  const rl = createInterface({ input: stream });

  for await (const line of rl) {
    if (!line) {
      continue;
    }
    let entry: any;
    try {
      entry = JSON.parse(line) as Record<string, unknown>;
    } catch (error) {
      console.warn('[dictionary:build] Failed to parse Kaikki line', (error as Error).message);
      continue;
    }

    if (entry.lang !== 'English' || typeof entry.word !== 'string') {
      continue;
    }

    const baseWord = entry.word.trim();
    if (!baseWord) {
      continue;
    }

    const formsSet = new Set<string>([baseWord]);
    ensureArray(entry.forms as any[] | undefined).forEach((form) => {
      if (form && typeof form.form === 'string') {
        const trimmed = form.form.trim();
        if (trimmed) {
          formsSet.add(trimmed);
        }
      }
    });

    const posSet = new Set<string>();
    if (typeof entry.pos === 'string' && entry.pos.trim()) {
      posSet.add(entry.pos.trim());
    }

    const pronunciation = collectPronunciations(entry.sounds as any[] | undefined);

    const englishGlosses = collectGlosses(entry.senses as any[] | undefined);
    if (englishGlosses.length) {
      enEntries.push({
        word: baseWord,
        definitions: englishGlosses,
        forms: Array.from(formsSet),
        pos: posSet.size ? Array.from(posSet) : undefined,
        pronunciation,
        source: `${source} (English gloss)`
      });
    }

    const chineseDefinitions = new Set<string>();
    const chineseWords = new Set<string>();
    const romanisations = new Set<string>();

    ensureArray(entry.translations as any[] | undefined).forEach((translation) => {
      if (!translation || typeof translation !== 'object') {
        return;
      }
      const langCode = typeof translation.lang_code === 'string' ? translation.lang_code : '';
      const lang = typeof translation.lang === 'string' ? translation.lang : '';
      const rawWord = typeof translation.word === 'string' ? translation.word : '';
      if (!rawWord || !containsHan(rawWord)) {
        return;
      }
      const isMandarin = langCode === 'cmn' || /Mandarin/i.test(lang);
      if (!isMandarin) {
        return;
      }

      const variants = splitChineseVariants(rawWord);
      const sense = typeof translation.sense === 'string' ? translation.sense.trim() : '';
      const roman = typeof translation.roman === 'string' ? translation.roman.trim() : '';

      variants.forEach((variant) => {
        if (!variant) {
          return;
        }
        chineseWords.add(variant);
        const definition = sense ? `${variant} — ${sense}` : variant;
        chineseDefinitions.add(definition);
      });

      if (roman) {
        romanisations.add(roman);
      }
    });

    if (!chineseDefinitions.size) {
      continue;
    }

    const dictEntry: DictionaryEntry = {
      word: baseWord,
      definitions: Array.from(chineseDefinitions),
      forms: Array.from(formsSet),
      pos: posSet.size ? Array.from(posSet) : undefined,
      pronunciation,
      source,
      metadata: romanisations.size ? { romanisations: Array.from(romanisations) } : undefined
    };
    enZhEntries.push(dictEntry);

    const chineseVariants = Array.from(chineseWords);
    if (chineseVariants.length) {
      const mapKeys = new Set<string>();
      formsSet.forEach((form) => {
        normalizeEnglishKey(form).forEach((key) => {
          if (key) {
            mapKeys.add(key);
          }
        });
      });

      mapKeys.forEach((key) => {
        const existing = translationMap.get(key) ?? [];
        const merged = new Set([...existing, ...chineseVariants]);
        translationMap.set(key, Array.from(merged));
      });
    }
  }

  return {
    source,
    enZhEntries,
    enEntries,
    translationMap
  };
};

const addToMap = (map: Map<string, string[]>, key: string, values: string[]): void => {
  if (!key) {
    return;
  }
  const existing = map.get(key) ?? [];
  const merged = new Set([...existing, ...values]);
  map.set(key, Array.from(merged));
};

const parseCedict = (content: string): CedictData => {
  const lines = content.split(/\r?\n/);
  const entries: DictionaryEntry[] = [];
  const translationMap = new Map<string, string[]>();
  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      return;
    }
    const match = trimmed.match(/^(\S+)\s+(\S+)\s+\[(.+?)\]\s+\/(.+)\/$/);
    if (!match) {
      return;
    }
    const [, traditional, simplified, pinyin, defsRaw] = match;
    const definitions = defsRaw
      .split('/')
      .map((def) => def.trim())
      .filter(Boolean);
    if (!definitions.length) {
      return;
    }

    const forms = simplified === traditional ? [simplified] : [simplified, traditional];
    entries.push({
      word: simplified,
      reading: simplified,
      pronunciation: pinyin,
      definitions,
      forms,
      source: 'CC-CEDICT (MDBG export)',
      metadata: {
        traditional,
        simplified,
        pinyin
      }
    });

    const chineseForms = Array.from(new Set(forms));
    definitions.forEach((definition) => {
      if (!definition) {
        return;
      }
      const withoutParens = definition.replace(/\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim();
      const clauses = withoutParens
        .split(/[,;]+/)
        .map((clause) => clause.trim())
        .filter(Boolean);
      clauses.forEach((clause) => {
        const withoutInfinitive = clause.replace(/^to\s+/, '');
        normalizeEnglishKey(withoutInfinitive).forEach((key) => addToMap(translationMap, key, chineseForms));
      });
    });
  });

  return {
    source: 'CC-CEDICT (MDBG export)',
    entries,
    translationMap
  };
};

const decodeJmPos = (posValue: string): string => {
  const trimmed = posValue.replace(/^&/, '').replace(/;$/, '');
  return JM_POS_MAP[trimmed] ?? trimmed;
};

const translateGlossToChinese = (gloss: string, translationMap: Map<string, string[]>): string[] => {
  const variants = normalizeEnglishKey(gloss);
  const results = new Set<string>();
  for (const variant of variants) {
    const matches = translationMap.get(variant);
    if (matches) {
      matches.forEach((value) => results.add(value));
    }
  }
  if (results.size) {
    return Array.from(results);
  }

  const tokens = variants
    .flatMap((variant) => variant.split(' '))
    .map((token) => token.trim())
    .filter((token) => token.length > 1 && !STOP_WORDS.has(token));

  tokens.forEach((token) => {
    const matches = translationMap.get(token) ?? translationMap.get(token.replace(/[^a-z'-]+/g, ''));
    if (matches) {
      matches.forEach((value) => results.add(value));
    }
  });

  return Array.from(results);
};

const parseJmdict = (xml: string, translationMap: Map<string, string[]>): JmdictData => {
  const parser = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: '',
    trimValues: true,
    removeNSPrefix: true,
    isArray: (name) =>
      [
        'entry',
        'k_ele',
        'keb',
        'r_ele',
        'reb',
        'sense',
        'gloss',
        'pos'
      ].includes(name)
  });

  const document = parser.parse(xml) as { JMdict?: { entry?: any[] } };
  const entriesRaw = ensureArray(document.JMdict?.entry);

  const jaEntries: DictionaryEntry[] = [];
  const jaZhEntries: DictionaryEntry[] = [];

  entriesRaw.forEach((entry) => {
    const kanjiElements = ensureArray(entry.k_ele ?? []);
    const readingElements = ensureArray(entry.r_ele ?? []);
    const primaryWord = (kanjiElements[0]?.keb?.[0] ?? readingElements[0]?.reb?.[0] ?? '').trim();
    if (!primaryWord) {
      return;
    }

    const forms = new Set<string>();
    kanjiElements.forEach((k) => ensureArray(k.keb ?? []).forEach((value) => forms.add(String(value).trim())));
    readingElements.forEach((r) => ensureArray(r.reb ?? []).forEach((value) => forms.add(String(value).trim())));

    const readings = readingElements
      .map((r) => ensureArray(r.reb ?? [])[0])
      .map((value) => String(value).trim())
      .filter(Boolean);

    const posSet = new Set<string>();
    const englishGlosses: string[] = [];
    const chineseGlosses: string[] = [];

    ensureArray(entry.sense ?? []).forEach((sense) => {
      ensureArray(sense.pos ?? []).forEach((posValue) => {
        const decoded = decodeJmPos(String(posValue).trim());
        if (decoded) {
          posSet.add(decoded);
        }
      });

      ensureArray(sense.gloss ?? []).forEach((glossValue) => {
        if (typeof glossValue === 'string') {
          const text = glossValue.trim();
          if (text) {
            englishGlosses.push(text);
          }
          return;
        }
        if (glossValue && typeof glossValue === 'object') {
          const text =
            typeof glossValue['#text'] === 'string'
              ? glossValue['#text'].trim()
              : typeof glossValue.text === 'string'
                ? glossValue.text.trim()
                : '';
          if (!text) {
            return;
          }
          if (!glossValue.lang || glossValue.lang === 'eng') {
            englishGlosses.push(text);
          } else if (glossValue.lang === 'zh' || glossValue.lang === 'zho' || glossValue.lang === 'cmn') {
            chineseGlosses.push(text);
          }
        }
      });
    });

    const pos = posSet.size ? Array.from(posSet) : undefined;
    const reading = readings[0];
    const baseEntry: Partial<DictionaryEntry> = {
      word: primaryWord,
      reading,
      forms: Array.from(forms)
    };

    if (englishGlosses.length) {
      jaEntries.push({
        ...baseEntry,
        word: primaryWord,
        reading,
        forms: Array.from(forms),
        pos,
        definitions: englishGlosses,
        source: 'JMdict (English glosses)',
        metadata: { englishGlosses }
      });
    }

    const aggregatedChinese = new Set<string>(chineseGlosses);
    if (!aggregatedChinese.size) {
      englishGlosses.forEach((gloss) => {
        translateGlossToChinese(gloss, translationMap).forEach((value) => aggregatedChinese.add(value));
      });
    }

    if (aggregatedChinese.size) {
      jaZhEntries.push({
        ...baseEntry,
        word: primaryWord,
        reading,
        forms: Array.from(forms),
        pos,
        definitions: Array.from(aggregatedChinese),
        source: 'JMdict + Kaikki (Chinese gloss)',
        metadata: { englishGlosses: englishGlosses.slice(0, 5) }
      });
    }
  });

  return {
    source: 'JMdict (Monash Nihongo archive)',
    jaEntries,
    jaZhEntries
  };
};

const loadKaikki = async (options: BuildOptions, context: BuildContext): Promise<KaikkiData> => {
  if (context.kaikki) {
    return context.kaikki;
  }
  const rawDir = await ensureRawDir(options);
  const archivePath = join(rawDir, KAIKKI_ARCHIVE.filename);
  await downloadFile(KAIKKI_ARCHIVE.url, archivePath, options.force);
  const data = await parseKaikki(archivePath);
  context.kaikki = data;
  return data;
};

const loadCedict = async (options: BuildOptions, context: BuildContext): Promise<CedictData> => {
  if (context.cedict) {
    return context.cedict;
  }
  const rawDir = await ensureRawDir(options);
  const archivePath = join(rawDir, CEDICT_ARCHIVE.filename);
  await downloadFile(CEDICT_ARCHIVE.url, archivePath, options.force);
  const content = await readGzipFile(archivePath);
  const data = parseCedict(content);
  context.cedict = data;
  return data;
};

const loadJmdict = async (options: BuildOptions, context: BuildContext): Promise<JmdictData> => {
  if (context.jmdict) {
    return context.jmdict;
  }
  const rawDir = await ensureRawDir(options);
  const archivePath = join(rawDir, JMDICT_ARCHIVE.filename);
  await downloadFile(JMDICT_ARCHIVE.url, archivePath, options.force);
  const xml = await readGzipFile(archivePath);
  const kaikki = await loadKaikki(options, context);
  const cedict = await loadCedict(options, context);
  const combinedMap = new Map<string, string[]>(kaikki.translationMap);
  cedict.translationMap.forEach((values, key) => addToMap(combinedMap, key, values));
  const data = parseJmdict(xml, combinedMap);
  context.jmdict = data;
  return data;
};

const builders: Record<DictionaryLanguage, Builder> = {
  'en-zh': async (options, context) => {
    if (options.mode === 'sample') {
      return SAMPLE_DICTIONARIES['en-zh']
        ? { entries: SAMPLE_DICTIONARIES['en-zh']!, source: 'sample' }
        : null;
    }
    const kaikki = await loadKaikki(options, context);
    return { entries: kaikki.enZhEntries, source: kaikki.source };
  },
  en: async (options, context) => {
    if (options.mode === 'sample') {
      return SAMPLE_DICTIONARIES.en ? { entries: SAMPLE_DICTIONARIES.en, source: 'sample' } : null;
    }
    const kaikki = await loadKaikki(options, context);
    return { entries: kaikki.enEntries, source: `${kaikki.source} (English gloss)` };
  },
  'ja-zh': async (options, context) => {
    if (options.mode === 'sample') {
      return SAMPLE_DICTIONARIES['ja-zh']
        ? { entries: SAMPLE_DICTIONARIES['ja-zh']!, source: 'sample' }
        : null;
    }
    const jmdict = await loadJmdict(options, context);
    return { entries: jmdict.jaZhEntries, source: `${jmdict.source} + Kaikki` };
  },
  ja: async (options, context) => {
    if (options.mode === 'sample') {
      return SAMPLE_DICTIONARIES.ja ? { entries: SAMPLE_DICTIONARIES.ja, source: 'sample' } : null;
    }
    const jmdict = await loadJmdict(options, context);
    return { entries: jmdict.jaEntries, source: jmdict.source };
  },
  zh: async (options, context) => {
    if (options.mode === 'sample') {
      return SAMPLE_DICTIONARIES.zh ? { entries: SAMPLE_DICTIONARIES.zh, source: 'sample' } : null;
    }
    const cedict = await loadCedict(options, context);
    return { entries: cedict.entries, source: cedict.source };
  }
};

const build = async (): Promise<void> => {
  const options = parseArgs();
  await ensureOutputDir();

  const context: BuildContext = {};
  const manifestEntries: ManifestEntry[] = [];

  for (const language of options.languages) {
    const builder = builders[language];
    if (!builder) {
      console.warn(`[dictionary:build] Unsupported language "${language}", skipping.`);
      continue;
    }

    try {
      const result = await builder(options, context);
      if (!result || !result.entries.length) {
        console.warn(`[dictionary:build] No entries produced for ${language}, skipping.`);
        continue;
      }

      const sqliteFilename = `${language}.sqlite`;
      const jsonFilename = `${language}.json.gz`;
      const sqlitePath = join(OUTPUT_DIR, sqliteFilename);
      const jsonPath = join(OUTPUT_DIR, jsonFilename);

      const count = await writeSqlite(language, result.entries, sqlitePath, options.force);
      await writeGzipJson(jsonPath, result.entries, options.force);

      const sqliteSha256 = await checksum(sqlitePath);
      const jsonSha256 = await checksum(jsonPath);

      manifestEntries.push({
        language,
        entries: count,
        sqlite: basename(sqlitePath),
        sqliteSha256,
        json: basename(jsonPath),
        jsonSha256,
        source: result.source
      });

      console.log(`[dictionary:build] Built ${language} dictionary with ${count} entries.`);
    } catch (error) {
      console.error(`[dictionary:build] Failed to build ${language}: ${(error as Error).message}`);
    }
  }

  if (!manifestEntries.length) {
    console.warn('[dictionary:build] No dictionaries generated.');
    return;
  }

  const manifest = {
    generatedAt: new Date().toISOString(),
    mode: options.mode,
    dictionaries: manifestEntries
  };

  await writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2), 'utf-8');
  console.log(`[dictionary:build] Manifest written to ${MANIFEST_PATH}`);
};

void build();
