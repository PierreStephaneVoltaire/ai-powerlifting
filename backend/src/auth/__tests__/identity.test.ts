/**
 * Smoke tests for the identity helpers (groupsFromSettings, isAppRole,
 * legacy-compat path). Run with:  npx tsx src/auth/__tests__/identity.test.ts
 */
import {
  groupsFromSettings,
  isAppRole,
  isAthlete,
  isCoach,
  isHandler,
  APP_ROLE_VALUES,
  ATHLETES_GROUP,
  COACHES_GROUP,
  HANDLERS_GROUP,
} from '../identity'

let failures = 0
function check(name: string, cond: boolean, info?: unknown): void {
  if (cond) {
    console.log(`  PASS  ${name}`)
  } else {
    failures++
    console.log(`  FAIL  ${name}: ${JSON.stringify(info)}`)
  }
}

function mkIdentity(
  overrides: Partial<{
    groups: string[]
    roles: string[]
    active_role: 'athlete' | 'coach' | 'handler' | null
  }> = {},
) {
  return {
    provider: 'discord' as const,
    sub: '1',
    username: 'u',
    display_name: 'u',
    avatar: null,
    groups: overrides.groups ?? [],
    roles: overrides.roles ?? [],
    active_role: overrides.active_role ?? null,
    email: null,
  }
}

// 1. isAppRole
check(
  'isAppRole accepts athlete/coach/handler',
  isAppRole('athlete') && isAppRole('coach') && isAppRole('handler'),
)
check('isAppRole rejects other strings', !isAppRole('admin') && !isAppRole('athletes') && !isAppRole(''))
check('isAppRole rejects null/undefined', !isAppRole(null) && !isAppRole(undefined))
check('APP_ROLE_VALUES has three entries', APP_ROLE_VALUES.length === 3)

// 2. groupsFromSettings — empty starting state
{
  const out = groupsFromSettings([], [], ['athlete'], 'athlete')
  check(
    'athlete alone adds athletes group + role + active',
    out.groups.includes(ATHLETES_GROUP) &&
      out.active_role === 'athlete' &&
      out.roles.includes('athlete'),
    out,
  )
}
{
  const out = groupsFromSettings([], [], ['coach'], 'coach')
  check(
    'coach alone adds coaches group + role + active',
    out.groups.includes(COACHES_GROUP) && out.active_role === 'coach' && out.roles.includes('coach'),
    out,
  )
}
{
  const out = groupsFromSettings([], [], ['handler'], 'handler')
  check(
    'handler alone adds handlers group + role + active',
    out.groups.includes(HANDLERS_GROUP) &&
      out.active_role === 'handler' &&
      out.roles.includes('handler'),
    out,
  )
}

// 3. multi-role
{
  const out = groupsFromSettings([], [], ['athlete', 'coach'], 'coach')
  check(
    'athlete+coach => both groups + active=coach',
    out.groups.includes(ATHLETES_GROUP) &&
      out.groups.includes(COACHES_GROUP) &&
      out.active_role === 'coach',
    out,
  )
}

// 4. legacy groups preserved
{
  const out = groupsFromSettings(['discord-admins', ATHLETES_GROUP], ['admin'], ['coach'], 'coach')
  check('legacy non-role groups preserved', out.groups.includes('discord-admins'), out)
  check(
    'legacy athlete group replaced by coach group',
    !out.groups.includes(ATHLETES_GROUP) && out.groups.includes(COACHES_GROUP),
    out,
  )
}

// 5. invalid active_role falls back to first declared
{
  const out = groupsFromSettings([], [], ['coach', 'handler'], 'admin')
  check('invalid active_role falls back to first valid role', out.active_role === 'coach', out)
}

// 6. empty settings => no active_role
{
  const out = groupsFromSettings([], [], [], 'athlete')
  check('no settings.roles => active_role is null', out.active_role === null, out)
  check('no settings.roles => no role groups added', !out.groups.includes(ATHLETES_GROUP), out)
}

// 7. unknown entries in settings.roles are ignored
{
  const out = groupsFromSettings([], [], ['athlete', 'unknown', null, 42], 'athlete')
  check('unknown entries ignored', out.roles.length === 1 && out.active_role === 'athlete', out)
}

// 8. isCoach / isHandler / isAthlete pick up the new group from settings
{
  const i = mkIdentity({ groups: [COACHES_GROUP], active_role: 'coach' })
  check('isCoach returns true when coaches group present', isCoach(i))
  check('isHandler returns false', !isHandler(i))
}
{
  const i = mkIdentity({ groups: [HANDLERS_GROUP], active_role: 'handler' })
  check('isHandler returns true when handlers group present', isHandler(i))
  check('isCoach returns false', !isCoach(i))
}
{
  const i = mkIdentity({ groups: [ATHLETES_GROUP], active_role: 'athlete' })
  check('isAthlete returns true when athletes group present', isAthlete(i))
}

console.log(`\n${failures === 0 ? 'OK' : `FAILED: ${failures}`}`)
process.exit(failures === 0 ? 0 : 1)
