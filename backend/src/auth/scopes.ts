export const SCOPES = [
  'profile',
  'sessions',
  'program',
  'competitions',
  'attempts',
  'budget',
  'analytics',
  'lift_profile',
  'maxes',
  'templates',
  'glossary',
  'videos',
  'exports',
  'grants',
] as const

export type Scope = (typeof SCOPES)[number]

export type Access = 'read' | 'write'

export function scopeKey(scope: Scope, access: Access): string {
  return `${scope}:${access}`
}

export const SCOPE_READ: Record<Scope, string> = Object.fromEntries(
  SCOPES.map((s) => [s, scopeKey(s, 'read')]),
) as Record<Scope, string>

export const SCOPE_WRITE: Record<Scope, string> = Object.fromEntries(
  SCOPES.map((s) => [s, scopeKey(s, 'write')]),
) as Record<Scope, string>

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface RouteScopeRule {
  method: HttpMethod
  path: string
  access: Access
  scope: Scope
  description: string
}

export const ROUTE_SCOPES: ReadonlyArray<RouteScopeRule> = [
  { method: 'GET', path: '/api/settings', access: 'read', scope: 'profile', description: 'Read own settings' },
  { method: 'PUT', path: '/api/settings/nickname', access: 'write', scope: 'profile', description: 'Update nickname' },
  { method: 'PUT', path: '/api/settings/profile', access: 'write', scope: 'profile', description: 'Update profile' },
  { method: 'POST', path: '/api/settings/avatar', access: 'write', scope: 'profile', description: 'Upload avatar' },
  { method: 'GET', path: '/api/profiles/search', access: 'read', scope: 'profile', description: 'Search public profiles' },
  { method: 'GET', path: '/api/profiles/:nickname', access: 'read', scope: 'profile', description: 'View public profile' },
  { method: 'GET', path: '/api/programs', access: 'read', scope: 'program', description: 'Read program' },
  { method: 'PUT', path: '/api/programs', access: 'write', scope: 'program', description: 'Update program' },
  { method: 'POST', path: '/api/programs', access: 'write', scope: 'program', description: 'Create program version' },
  { method: 'POST', path: '/api/programs/apply-template', access: 'write', scope: 'program', description: 'Apply template' },
  { method: 'GET', path: '/api/sessions', access: 'read', scope: 'sessions', description: 'List sessions' },
  { method: 'PUT', path: '/api/sessions', access: 'write', scope: 'sessions', description: 'Update session' },
  { method: 'POST', path: '/api/sessions', access: 'write', scope: 'sessions', description: 'Create session' },
  { method: 'DELETE', path: '/api/sessions', access: 'write', scope: 'sessions', description: 'Delete session' },
  { method: 'GET', path: '/api/exercises', access: 'read', scope: 'sessions', description: 'Read exercises' },
  { method: 'PUT', path: '/api/exercises', access: 'write', scope: 'sessions', description: 'Update exercise' },
  { method: 'POST', path: '/api/exercises', access: 'write', scope: 'sessions', description: 'Create exercise' },
  { method: 'GET', path: '/api/maxes', access: 'read', scope: 'maxes', description: 'Read maxes' },
  { method: 'PUT', path: '/api/maxes', access: 'write', scope: 'maxes', description: 'Update maxes' },
  { method: 'POST', path: '/api/maxes', access: 'write', scope: 'maxes', description: 'Create max record' },
  { method: 'GET', path: '/api/weight', access: 'read', scope: 'profile', description: 'Read weight log' },
  { method: 'POST', path: '/api/weight', access: 'write', scope: 'profile', description: 'Log weight' },
  { method: 'DELETE', path: '/api/weight', access: 'write', scope: 'profile', description: 'Delete weight' },
  { method: 'GET', path: '/api/supplements', access: 'read', scope: 'profile', description: 'Read supplements' },
  { method: 'PUT', path: '/api/supplements', access: 'write', scope: 'profile', description: 'Update supplements' },
  { method: 'GET', path: '/api/diet-notes', access: 'read', scope: 'profile', description: 'Read diet notes' },
  { method: 'PUT', path: '/api/diet-notes', access: 'write', scope: 'profile', description: 'Update diet notes' },
  { method: 'GET', path: '/api/block-notes', access: 'read', scope: 'program', description: 'Read block notes' },
  { method: 'PUT', path: '/api/block-notes', access: 'write', scope: 'program', description: 'Update block notes' },
  { method: 'GET', path: '/api/competitions', access: 'read', scope: 'competitions', description: 'List competitions' },
  { method: 'POST', path: '/api/competitions', access: 'write', scope: 'competitions', description: 'Register for competition' },
  { method: 'PUT', path: '/api/competitions', access: 'write', scope: 'competitions', description: 'Update competition entry' },
  { method: 'DELETE', path: '/api/competitions', access: 'write', scope: 'competitions', description: 'Remove competition entry' },
  { method: 'PUT', path: '/api/competitions/attempts', access: 'write', scope: 'attempts', description: 'Set attempt selection' },
  { method: 'GET', path: '/api/goals', access: 'read', scope: 'program', description: 'Read goals' },
  { method: 'PUT', path: '/api/goals', access: 'write', scope: 'program', description: 'Update goals' },
  { method: 'GET', path: '/api/federations', access: 'read', scope: 'program', description: 'Read federations' },
  { method: 'PUT', path: '/api/federations', access: 'write', scope: 'program', description: 'Update federations' },
  { method: 'GET', path: '/api/budget', access: 'read', scope: 'budget', description: 'Read budget' },
  { method: 'POST', path: '/api/budget/items', access: 'write', scope: 'budget', description: 'Add budget item' },
  { method: 'PUT', path: '/api/budget/items', access: 'write', scope: 'budget', description: 'Update budget item' },
  { method: 'DELETE', path: '/api/budget/items', access: 'write', scope: 'budget', description: 'Delete budget item' },
  { method: 'POST', path: '/api/budget/ai-analysis', access: 'read', scope: 'budget', description: 'AI budget advisor (read-only projection)' },
  { method: 'GET', path: '/api/analytics/analysis/sections', access: 'read', scope: 'analytics', description: 'Deterministic analysis sections' },
  { method: 'POST', path: '/api/analytics/analysis/sections/queue', access: 'read', scope: 'analytics', description: 'Queue analysis section' },
  { method: 'GET', path: '/api/analytics/block-comparison', access: 'read', scope: 'analytics', description: 'Block comparison' },
  { method: 'POST', path: '/api/analytics/block-comparison/ai', access: 'read', scope: 'analytics', description: 'AI block comparison (read-only)' },
  { method: 'GET', path: '/api/analytics/budget/timeline', access: 'read', scope: 'budget', description: 'Budget timeline' },
  { method: 'POST', path: '/api/analytics/budget/timeline', access: 'read', scope: 'budget', description: 'Budget timeline recompute' },
  { method: 'GET', path: '/api/lift-profiles/:lift', access: 'read', scope: 'lift_profile', description: 'Read lift profile' },
  { method: 'PUT', path: '/api/lift-profiles/:lift', access: 'write', scope: 'lift_profile', description: 'Update lift profile' },
  { method: 'GET', path: '/api/videos', access: 'read', scope: 'videos', description: 'List videos' },
  { method: 'POST', path: '/api/videos', access: 'write', scope: 'videos', description: 'Upload video' },
  { method: 'PATCH', path: '/api/videos/:id/thumbnail', access: 'write', scope: 'videos', description: 'Patch video thumbnail status' },
  { method: 'GET', path: '/api/videos/media/:path', access: 'read', scope: 'videos', description: 'Stream video' },
  { method: 'GET', path: '/api/templates', access: 'read', scope: 'templates', description: 'List templates' },
  { method: 'POST', path: '/api/templates', access: 'write', scope: 'templates', description: 'Create template' },
  { method: 'PUT', path: '/api/templates', access: 'write', scope: 'templates', description: 'Update template' },
  { method: 'DELETE', path: '/api/templates', access: 'write', scope: 'templates', description: 'Delete template' },
  { method: 'POST', path: '/api/templates/import', access: 'write', scope: 'templates', description: 'Import template' },
  { method: 'GET', path: '/api/glossary', access: 'read', scope: 'glossary', description: 'Read glossary' },
  { method: 'PUT', path: '/api/glossary', access: 'write', scope: 'glossary', description: 'Update glossary' },
  { method: 'GET', path: '/api/export', access: 'read', scope: 'exports', description: 'Export data' },
  { method: 'POST', path: '/api/import', access: 'write', scope: 'program', description: 'Import program' },
  { method: 'GET', path: '/api/grants', access: 'read', scope: 'grants', description: 'List grants' },
  { method: 'POST', path: '/api/grants', access: 'write', scope: 'grants', description: 'Issue grant' },
  { method: 'DELETE', path: '/api/grants/:id', access: 'write', scope: 'grants', description: 'Revoke grant' },
]

export function findRouteRule(method: HttpMethod, path: string): RouteScopeRule | null {
  for (const rule of ROUTE_SCOPES) {
    if (rule.method !== method) continue
    if (matchPath(rule.path, path)) return rule
  }
  return null
}

function matchPath(pattern: string, actual: string): boolean {
  const patternParts = pattern.split('/').filter(Boolean)
  const actualParts = actual.split('/').filter(Boolean)
  if (patternParts.length !== actualParts.length) return false
  for (let i = 0; i < patternParts.length; i++) {
    if (patternParts[i].startsWith(':')) continue
    if (patternParts[i] !== actualParts[i]) return false
  }
  return true
}
