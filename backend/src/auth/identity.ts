export type IdentityProvider = 'discord' | 'authentik'

export interface AuthGroups {
  groups: string[]
  roles: string[]
}

export interface AuthIdentity {
  provider: IdentityProvider
  sub: string
  username: string
  display_name: string
  avatar: string | null
  groups: string[]
  roles: string[]
  email?: string | null
}

export const ATHLETES_GROUP = 'athletes'
export const COACHES_GROUP = 'coaches'
export const HANDLERS_GROUP = 'handlers'

export const ATHLETE_ROLE = 'athletes'
export const COACH_ROLE = 'coaches'
export const HANDLER_ROLE = 'handlers'

export const OPERATOR_MAPPED_PK = 'operator'

export function isCoach(identity: AuthIdentity | null | undefined): boolean {
  if (!identity) return false
  return identity.groups.includes(COACHES_GROUP) || identity.roles.includes(COACH_ROLE)
}

export function isHandler(identity: AuthIdentity | null | undefined): boolean {
  if (!identity) return false
  return identity.groups.includes(HANDLERS_GROUP) || identity.roles.includes(HANDLER_ROLE)
}

export function isAthlete(identity: AuthIdentity | null | undefined): boolean {
  if (!identity) return false
  return identity.groups.includes(ATHLETES_GROUP) || identity.roles.includes(ATHLETE_ROLE) || (!isCoach(identity) && !isHandler(identity))
}

export function primaryGroup(identity: AuthIdentity | null | undefined): 'athlete' | 'coach' | 'handler' | 'guest' {
  if (!identity) return 'guest'
  if (isCoach(identity)) return 'coach'
  if (isHandler(identity)) return 'handler'
  if (isAthlete(identity)) return 'athlete'
  return 'guest'
}
