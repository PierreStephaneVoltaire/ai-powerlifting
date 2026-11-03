const ownContextRoutes = new Set(['/', '/profile', '/profiles', '/roster', '/inbox', '/settings'])

export function shouldRestoreOwnContext(pathname: string, mappedPk: string | null | undefined, ownPk: string | null | undefined): boolean {
  return ownContextRoutes.has(pathname) && Boolean(mappedPk && ownPk && mappedPk !== ownPk)
}
