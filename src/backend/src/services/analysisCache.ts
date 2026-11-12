export type AnalysisWindowKey =
  | 'current'
  | 'previous_1'
  | 'previous_2'
  | 'previous_4'
  | 'previous_8'
  | 'block'

export type AnalysisSectionKey =
  | 'overview'
  | 'fatigue_readiness'
  | 'peaking'
  | 'workload'
  | 'alerts'
  | 'ai_correlation'
  | 'program_evaluation'

const ALL_WINDOW_KEY_SET = new Set<string>(['current', 'previous_1', 'previous_2', 'previous_4', 'previous_8', 'block'])
const ALL_SECTION_KEYS: AnalysisSectionKey[] = ['overview', 'fatigue_readiness', 'peaking', 'workload', 'alerts', 'ai_correlation', 'program_evaluation']
const ALL_SECTION_KEY_SET = new Set<string>(ALL_SECTION_KEYS)

export function normalizeAnalysisWindowKey(value: unknown): AnalysisWindowKey {
  return typeof value === 'string' && ALL_WINDOW_KEY_SET.has(value)
    ? value as AnalysisWindowKey
    : 'current'
}

export function normalizeAnalysisSectionKeys(
  value: unknown,
  fallback: AnalysisSectionKey[] = ALL_SECTION_KEYS,
): AnalysisSectionKey[] {
  if (!Array.isArray(value)) return fallback
  const filtered = value.filter((v): v is AnalysisSectionKey => typeof v === 'string' && ALL_SECTION_KEY_SET.has(v))
  return filtered.length ? filtered : fallback
}

export function isIsoDate(value: string | undefined): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
}
