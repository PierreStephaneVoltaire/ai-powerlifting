export const SCOPES = ['profile', 'program', 'sessions', 'competition', 'federation', 'glossary', 'goals', 'budget', 'calculations', 'performance', 'weight-log', 'templates', 'imports', 'lift-profiles', 'analytics', 'videos', 'settings', 'grants', 'operator'] as const
export type Scope = (typeof SCOPES)[number]
export type Access = 'read' | 'write'
export type HttpMethod = 'GET' | 'HEAD' | 'OPTIONS' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
export const scopeKey = (scope: Scope, access: Access): string => `${scope}:${access}`
export const SCOPE_READ = Object.fromEntries(SCOPES.map(scope => [scope, scopeKey(scope, 'read')])) as Record<Scope, string>
export const SCOPE_WRITE = Object.fromEntries(SCOPES.map(scope => [scope, scopeKey(scope, 'write')])) as Record<Scope, string>

export const ROUTE_SCOPES: Record<string, Scope> = {
  programs: 'program', sessions: 'sessions', exercises: 'glossary', maxes: 'performance', weight: 'weight-log',
  supplements: 'program', 'diet-notes': 'program', 'block-notes': 'program', competitions: 'competition',
  goals: 'goals', federations: 'federation', budget: 'budget', analytics: 'analytics', videos: 'videos',
  templates: 'templates', export: 'program', import: 'imports', grants: 'grants', settings: 'settings', onboarding: 'settings', setup: 'settings', stats: 'analytics', jobs: 'settings',
}

export function findRouteRule(method: HttpMethod, path: string, query: Record<string, unknown> = {}): { scope: Scope; access: Access } | null {
  const segments = path.split('/').filter(Boolean)
  if (segments[0] !== 'api') return null
  let scope = ROUTE_SCOPES[segments[1]]
  if (segments[1] === 'programs' && segments[3] === 'lift-profiles') scope = 'lift-profiles'
  if (segments[1] === 'grants' && segments.length > 2 && !path.endsWith('/requests/revoke')) scope = 'settings'
  if (!scope) return null
  let access: Access = ['GET', 'HEAD', 'OPTIONS'].includes(method) ? 'read' : 'write'
  if (segments[1] === 'templates' && segments[3] === 'apply') access = 'read'
  const report = /\/(program-evaluation|correlation|ai-analysis|ai)$/.test(path)
  if (report) access = (query.cacheOnly === 'true' || query.cache_only === 'true' || (path.endsWith('/ai-analysis') && query.refresh === 'false')) && query.refresh !== 'true' ? 'read' : 'write'
  if (query.refresh === 'true') access = 'write'
  if (path === '/api/analytics/budget/timeline') access = 'read'
  return { scope, access }
}
