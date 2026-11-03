type SessionIdentity = { id?: string; date: string }

export function sessionRoute(session: SessionIdentity, index: number): string {
  const path = `/session/${encodeURIComponent(session.date)}`
  if (session.id) return `${path}?session=${encodeURIComponent(session.id)}`
  return index >= 0 ? `${path}/${index}` : path
}

export function sessionIndexForRoute(sessions: SessionIdentity[], date: string, index?: string, id?: string | null): number {
  if (id) return sessions.findIndex((session) => session.id === id)
  if (index !== undefined) {
    if (!/^\d+$/.test(index)) return -1
    const parsed = Number(index)
    return sessions[parsed]?.date === date ? parsed : -1
  }
  const matches = sessions.flatMap((session, i) => session.date === date ? [i] : [])
  return matches.length === 1 ? matches[0] : -1
}
