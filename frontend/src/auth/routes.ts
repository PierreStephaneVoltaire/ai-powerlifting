export function routePermission(path: string): string | null {
  if (/^\/(login|auth|onboarding|about|profiles)(\/|$)/.test(path) || path === '/') return null
  if (/^\/(profile|roster|inbox|my-notes)(\/|$)/.test(path)) return 'settings:read'
  if (/^\/(sessions|calendar|session|list)(\/|$)/.test(path)) return 'sessions:read'
  if (path === '/athlete') return 'competition:read'
  if (path.startsWith('/lift-profiles')) return 'lift-profiles:read'
  if (/^\/(analysis|rankings|maxes)(\/|$)/.test(path)) return 'analytics:read'
  if (/^\/(biometrics|diet)(\/|$)/.test(path) || path === '/tools/weight') return 'weight-log:read'
  if (path.startsWith('/tools/attempts')) return 'competition:read'
  if (path.startsWith('/tools')) return null
  if (path.startsWith('/designer/goals')) return 'goals:read'
  if (path.startsWith('/designer/federations')) return 'federation:read'
  if (path.startsWith('/designer/competitions')) return 'competition:read'
  if (path.startsWith('/designer/glossary')) return 'glossary:read'
  if (path.startsWith('/designer/templates/new') || path.startsWith('/designer/template/edit') || /^\/designer\/templates\/.+\/edit$/.test(path)) return 'templates:write'
  if (path.startsWith('/designer/import') || path.startsWith('/designer/templates/import')) return 'imports:write'
  if (path.startsWith('/designer/template')) return 'templates:read'
  if (path.startsWith('/designer')) return 'program:write'
  if (path.startsWith('/budget')) return 'budget:read'
  if (path.startsWith('/videos')) return 'videos:read'
  if (/^\/(notes|log|supplements)(\/|$)/.test(path)) return 'program:read'
  return 'unmapped:read'
}
