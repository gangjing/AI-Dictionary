// AI Dictionary — Shared TypeScript / Rust IPC Contracts (EP-01 ~ EP-09)

export interface SenseItem {
  pos: string;
  zh: string;
  en: string;
  source_id: string;
}

export interface ExampleItem {
  en: string;
  zh: string;
  source_id: string;
}

export interface DictionaryEntry {
  id: string;
  lemma: string;
  lang: 'en' | 'zh';
  ipa_uk?: string | null;
  ipa_us?: string | null;
  senses: SenseItem[];
  forms: Record<string, string>;
  examples: ExampleItem[];
  source_id: string;
  source_version: string;
  matched_via?: string;
}

export interface LookupResponse {
  found: boolean;
  query: string;
  elapsed_ms: number;
  entry?: DictionaryEntry;
  suggestions?: string[];
}

export interface SavedWord {
  id: string;
  entry_id?: string | null;
  source_text: string;
  source_lang: string;
  target_lang: string;
  summary_snapshot: string;
  source_id: string;
  note: string;
  tags: string[];
  saved_at: string;
  updated_at: string;
}

export interface QueryHistoryItem {
  id: string;
  kind: 'lookup' | 'translate' | 'ocr';
  input_text: string;
  result_excerpt: string;
  source_lang: string;
  target_lang: string;
  created_at: string;
}

export interface ModelInfo {
  id: string;
  model_name: string;
  quant: string;
  file_path: string;
  sha256: string;
  size_bytes: number;
  recommended_ram_gb: number;
  license: string;
  status: 'not_installed' | 'downloading' | 'ready' | 'corrupted';
  is_active: boolean;
  installed_at?: string | null;
}

export interface TranslationRequest {
  requestId: string;
  text: string;
  sourceLang: 'auto' | 'en' | 'zh';
  targetLang: 'en' | 'zh';
  style?: 'general' | 'technical' | 'business';
  glossary?: Record<string, string>;
  preserveFormat?: boolean;
}

export interface TranslationChunkEvent {
  requestId: string;
  chunk: string;
  done: boolean;
  cancelled?: boolean;
  elapsedMs: number;
  protectedTokensVerified?: boolean;
  modelId: string;
  promptVersion: string;
}

export interface SelectionCaptureResult {
  status: 'ok' | 'permission_required' | 'blocked_secure_input' | 'empty_selection' | 'no_focused_element';
  appName?: string | null;
  bundleId?: string | null;
  role?: string | null;
  subrole?: string | null;
  isSecureField: boolean;
  selectedText?: string | null;
  method: string;
  message: string;
}

export interface OCRLine {
  text: string;
  confidence: number;
}

export interface OCRResult {
  status: string;
  elapsedMs: number;
  lines: OCRLine[];
  persistedToDisk: boolean;
}
