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
  active_role?: AppRole | null
  email?: string | null
}

export const ATHLETES_GROUP = 'athletes'
export const COACHES_GROUP = 'coaches'
export const HANDLERS_GROUP = 'handlers'

export const ATHLETE_ROLE = 'athletes'
export const COACH_ROLE = 'coaches'
export const HANDLER_ROLE = 'handlers'

export const OPERATOR_MAPPED_PK = 'operator'

// =============================================================================
// Epic 3 — Self-declared app role (settings.roles + settings.active_role).
// These functions compute the derived Discord group name from the user's
// onboarding choices. They DO NOT replace the legacy guild-based `groups` and
// `roles` checks above; they're additive so existing flows keep working.
// =============================================================================

export type AppRole = 'athlete' | 'coach' | 'handler'

export const APP_ROLE_VALUES: ReadonlyArray<AppRole> = ['athlete', 'coach', 'handler']

export function isAppRole(value: unknown): value is AppRole {
  return (
    typeof value === 'string' &&
    (APP_ROLE_VALUES as ReadonlyArray<string>).includes(value)
  )
}

function appRoleToGroup(role: AppRole): string {
  switch (role) {
    case 'athlete':
      return ATHLETES_GROUP
    case 'coach':
      return COACHES_GROUP
    case 'handler':
      return HANDLERS_GROUP
  }
}

/**
 * Compute the auth claim groups/active_role from a settings record.
 * The resulting groups are additive to whatever the IdP supplied — the user
 * keeps their Discord guild groups if any, plus a group for each self-declared
 * role.
 */
export function groupsFromSettings(
  existingGroups: string[],
  existingRoles: string[],
  settingsRoles: readonly unknown[] | undefined,
  activeRole: unknown,
): { groups: string[]; roles: string[]; active_role: AppRole | null } {
  const validAppRoles: AppRole[] = []
  if (Array.isArray(settingsRoles)) {
    for (const item of settingsRoles) {
      if (isAppRole(item) && !validAppRoles.includes(item)) validAppRoles.push(item)
    }
  }
  const ar: AppRole | null = isAppRole(activeRole) ? activeRole : null
  const effectiveActive: AppRole | null = ar && validAppRoles.includes(ar) ? ar : (validAppRoles[0] ?? null)
  // Strip the legacy plural groups — they'll be re-added based on app roles.
  const legacyGroupsStripped = existingGroups.filter(
    (g) => g !== ATHLETES_GROUP && g !== COACHES_GROUP && g !== HANDLERS_GROUP,
  )
  const groups = [...legacyGroupsStripped]
  for (const role of validAppRoles) {
    if (!groups.includes(appRoleToGroup(role))) groups.push(appRoleToGroup(role))
  }
  const roles = [...existingRoles]
  for (const role of validAppRoles) {
    if (!roles.includes(role)) roles.push(role)
  }
  return { groups, roles, active_role: effectiveActive }
}

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
