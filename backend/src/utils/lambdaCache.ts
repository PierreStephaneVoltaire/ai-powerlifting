import { createHash } from 'crypto'
import { invokeLambda } from './lambda'

export const DEFAULT_TTL = 120
export const MATH_TTL = 1800
export const AI_READ_TTL = 600
export const IMPORT_EXPORT_TTL = 300

const CACHE_CAP = 2048

type CacheEntry = { value: unknown; expires: number }
const cache = new Map<string, CacheEntry>()

export const MATH_TOOLS = new Set<string>([
  'kg_to_lb',
  'lb_to_kg',
  'ipf_weight_classes',
  'pct_of_max',
  'days_until',
  'estimate_1rm',
  'calculate_dots',
  'calculate_attempts',
  'analyze_progression',
  'analyze_rpe_drift',
  'powerlifting_filter_categories',
  'powerlifting_ranking_percentile',
  'analyze_powerlifting_stats',
])

export const AI_READ_TOOLS = new Set<string>([
  'correlation_analysis',
  'block_correlation_analysis',
  'weekly_analysis',
  'analysis_section',
  'regenerate_analysis',
  'get_analysis_markdown',
  'program_evaluation',
  'block_program_evaluation',
  'multi_block_comparison_analysis',
  'lift_profile_review',
  'muscle_group_estimate',
  'glossary_generate_text',
  'fatigue_profile_estimate',
])

export const IMPORT_EXPORT_TOOLS = new Set<string>([
  'import_parse_file',
  'import_list_pending',
  'import_get_pending',
  'export_program_markdown',
])

export const READ_TOOLS = new Set<string>([
  ...MATH_TOOLS,
  ...AI_READ_TOOLS,
  'import_list_pending',
  'import_get_pending',
  'template_list',
  'template_get',
  'health_setup_status',
  'export_program_markdown',
  'get_analysis_markdown',
])

export const WRITE_TOOLS = new Set<string>([
  'import_apply',
  'import_reject',
  'template_create_from_block',
  'template_create_blank',
  'template_update',
  'template_copy',
  'template_archive',
  'template_unarchive',
  'template_apply',
  'template_apply_confirm',
  'template_publish',
  'template_unpublish',
  'health_setup_initialize',
  'health_complete_competition',
  'health_snapshot_competition_projection',
  'health_invalidate_program_cache',
])

function ttlFor(functionName: string): number {
  if (MATH_TOOLS.has(functionName)) return MATH_TTL
  if (AI_READ_TOOLS.has(functionName)) return AI_READ_TTL
  if (IMPORT_EXPORT_TOOLS.has(functionName)) return IMPORT_EXPORT_TTL
  return DEFAULT_TTL
}

function cacheKey(pk: string, functionName: string, args: Record<string, unknown>): string {
  const hash = createHash('sha256').update(JSON.stringify(args)).digest('hex')
  return `${pk}:${functionName}:${hash}`
}

export async function cachedInvokeLambda(
  functionName: string,
  args: Record<string, unknown>,
  pk: string,
  ttlSeconds?: number,
): Promise<any> {
  const ttl = ttlSeconds ?? ttlFor(functionName)
  const now = Date.now()
  const key = cacheKey(pk, functionName, args)

  const hit = cache.get(key)
  if (hit && hit.expires > now) {
    cache.delete(key)
    cache.set(key, hit)
    return hit.value
  }
  cache.delete(key)

  const value = await invokeLambda(functionName, args)
  cache.set(key, { value, expires: now + ttl * 1000 })

  while (cache.size > CACHE_CAP) {
    const oldest = cache.keys().next().value
    if (oldest === undefined) break
    cache.delete(oldest)
  }

  return value
}

export function invalidateLambdaCache(pk: string, functionNamePrefix?: string): number {
  let removed = 0
  for (const key of Array.from(cache.keys())) {
    if (!key.startsWith(`${pk}:`)) continue
    if (functionNamePrefix !== undefined && !key.startsWith(`${pk}:${functionNamePrefix}`)) continue
    cache.delete(key)
    removed++
  }
  return removed
}