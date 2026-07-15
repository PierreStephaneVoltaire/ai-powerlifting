import { invokeLambda } from '../utils/lambda'
import { seedMasterCopiesForNewUser } from './masterCopy'
import type { AgeCategory, Role } from '@powerlifting/types'
import { ROLE_VALUES } from '@powerlifting/types'

const AGE_CATEGORY_VALUES: ReadonlyArray<AgeCategory> = [
  'open',
  'subjunior',
  'junior',
  'master1',
  'master2',
  'master3',
  'master4',
]

export type ProfileVisibility = 'private' | 'public'

export interface ProfileTag {
  tag: string
  approved: boolean
  proposed_by: string
}

export interface TrainingMaxes {
  squat_kg: number
  bench_kg: number
  deadlift_kg: number
}

export interface UserSettings {
  pk: string
  mapped_pk?: string
  username: string
  discord_id: string
  discord_username: string
  avatar_url: string | null
  nickname: string
  profile_visibility: ProfileVisibility
  display_name: string
  bio: string
  public_training_summary_enabled: boolean
  ranking_country: string | null
  ranking_region: string | null
  age_class: AgeCategory
  tags: ProfileTag[]
  sex: 'male' | 'female' | null
  bodyweight_kg: number | null
  training_maxes: TrainingMaxes | null
  federations: string[]
  roles: Role[]
  active_role: Role
  athlete_basics_complete: boolean
  profile_complete: boolean
  created_at: string
  updated_at: string
}

export interface PublicProfile {
  nickname: string
  display_name: string
  avatar_url: string | null
  bio: string
  profile_visibility: ProfileVisibility
  public_training_summary_enabled: boolean
  is_self: boolean
  tags: string[]
}

const CACHE_TTL_MS = 60_000
const cache = new Map<string, { settings: UserSettings; expires: number }>()

const NICKNAME_RE = /^[a-z0-9_-]{2,32}$/
const MAPPED_PK_RE = /^[A-Za-z0-9:_#-]{1,128}$/

export function validateNickname(nickname: string): boolean {
  return NICKNAME_RE.test(nickname)
}

function validateMappedPk(mappedPk: string): boolean {
  return MAPPED_PK_RE.test(mappedPk)
}

function sanitizeUsername(username: string): string {
  const sanitized = username.toLowerCase().replace(/[^a-z0-9_-]/g, '_').slice(0, 32)
  return validateNickname(sanitized) ? sanitized : `user_${Date.now()}`
}

function usernameKey(discordUsername: string): string {
  return sanitizeUsername(discordUsername)
}

function settingsUsernameKey(settings: UserSettings): string {
  return settings.username || usernameKey(settings.discord_username || settings.nickname)
}

function normalizeVisibility(value: unknown): ProfileVisibility {
  return value === 'public' ? 'public' : 'private'
}

function normalizeDisplayName(value: unknown, fallback: string): string {
  const displayName = typeof value === 'string' ? value.trim() : ''
  return displayName.slice(0, 80) || fallback
}

function normalizeBio(value: unknown): string {
  const bio = typeof value === 'string' ? value.trim() : ''
  return bio.slice(0, 280)
}

function normalizeMappedPk(value: unknown): string | undefined {
  const mappedPk = typeof value === 'string' ? value.trim() : ''
  return validateMappedPk(mappedPk) ? mappedPk : undefined
}

function normalizeAgeClass(value: unknown): AgeCategory {
  return typeof value === 'string' && AGE_CATEGORY_VALUES.includes(value as AgeCategory)
    ? (value as AgeCategory)
    : 'open'
}

const TAG_RE = /^[a-z0-9_-]{1,30}$/
const MAX_TAGS = 20

function normalizeTag(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  const tag = raw.trim().toLowerCase().replace(/\s+/g, '-').slice(0, 30)
  return TAG_RE.test(tag) ? tag : null
}

function normalizeTags(raw: unknown): ProfileTag[] {
  if (!Array.isArray(raw)) return []
  const seen = new Set<string>()
  const result: ProfileTag[] = []
  for (const item of raw) {
    let tag: string | null
    let approved: boolean
    let proposedBy: string
    if (typeof item === 'object' && item !== null) {
      tag = normalizeTag((item as Record<string, unknown>).tag)
      approved = Boolean((item as Record<string, unknown>).approved)
      proposedBy = String((item as Record<string, unknown>).proposed_by || '')
    } else if (typeof item === 'string') {
      tag = normalizeTag(item)
      approved = true
      proposedBy = ''
    } else {
      continue
    }
    if (!tag || seen.has(tag)) continue
    seen.add(tag)
    result.push({ tag, approved, proposed_by: proposedBy })
  }
  return result.slice(0, MAX_TAGS)
}

function normalizeRole(value: unknown): Role | null {
  return typeof value === 'string' && (ROLE_VALUES as ReadonlyArray<string>).includes(value)
    ? (value as Role)
    : null
}

function normalizeRoles(value: unknown): Role[] {
  if (!Array.isArray(value)) return []
  const seen: Role[] = []
  for (const item of value) {
    const role = normalizeRole(item)
    if (role && !seen.includes(role)) seen.push(role)
  }
  return seen
}

function normalizePositiveNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) return value
  if (typeof value === 'string') {
    const n = Number(value)
    if (Number.isFinite(n) && n > 0) return n
  }
  return null
}

function normalizeTrainingMaxes(value: unknown): TrainingMaxes | null {
  if (!value || typeof value !== 'object') return null
  const obj = value as Record<string, unknown>
  const squat = normalizePositiveNumber(obj.squat_kg)
  const bench = normalizePositiveNumber(obj.bench_kg)
  const deadlift = normalizePositiveNumber(obj.deadlift_kg)
  if (squat === null || bench === null || deadlift === null) return null
  return { squat_kg: squat, bench_kg: bench, deadlift_kg: deadlift }
}

function normalizeFederations(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const seen: string[] = []
  for (const item of value) {
    if (typeof item === 'string') {
      const v = item.trim()
      if (v && !seen.includes(v)) seen.push(v)
    }
  }
  return seen
}

function deriveActiveRole(roles: Role[], explicit: unknown): Role {
  const fromExplicit = normalizeRole(explicit)
  if (fromExplicit && roles.includes(fromExplicit)) return fromExplicit
  return roles[0] ?? 'athlete'
}

function normalizeSettings(raw: Record<string, unknown>): UserSettings {
  const discordUsername = String(raw.discord_username || raw.username || '')
  const username = usernameKey(String(raw.username || discordUsername || raw.nickname || 'user'))
  const nickname = String(raw.nickname || username)
  const pk = String(raw.pk || username)
  const mappedPk = normalizeMappedPk(raw.mapped_pk)
  const roles = normalizeRoles(raw.roles)
  const sexRaw = raw.sex
  const sex: 'male' | 'female' | null =
    sexRaw === 'male' || sexRaw === 'female' ? sexRaw : null
  return {
    pk,
    ...(mappedPk ? { mapped_pk: mappedPk } : {}),
    username,
    discord_id: String(raw.discord_id || ''),
    discord_username: discordUsername,
    avatar_url: typeof raw.avatar_url === 'string' ? raw.avatar_url : null,
    nickname,
    profile_visibility: normalizeVisibility(raw.profile_visibility),
    display_name: normalizeDisplayName(raw.display_name, discordUsername || nickname),
    bio: normalizeBio(raw.bio),
    public_training_summary_enabled: raw.public_training_summary_enabled === true,
    ranking_country: typeof raw.ranking_country === 'string' ? raw.ranking_country : null,
    ranking_region: typeof raw.ranking_region === 'string' ? raw.ranking_region : null,
    age_class: normalizeAgeClass(raw.age_class),
    tags: normalizeTags(raw.tags),
    sex,
    bodyweight_kg: normalizePositiveNumber(raw.bodyweight_kg),
    training_maxes: normalizeTrainingMaxes(raw.training_maxes),
    federations: normalizeFederations(raw.federations),
    roles,
    active_role: deriveActiveRole(roles, raw.active_role),
    athlete_basics_complete: raw.athlete_basics_complete === true,
    profile_complete: raw.profile_complete === true,
    created_at: String(raw.created_at || new Date().toISOString()),
    updated_at: String(raw.updated_at || new Date().toISOString()),
  }
}

function isSelfProfile(settings: UserSettings, viewerUsername?: string): boolean {
  const viewerKey = viewerUsername ? usernameKey(viewerUsername) : ''
  return Boolean(viewerKey && viewerKey === (settings.username || ''))
}

function canViewProfile(settings: UserSettings, viewerUsername?: string): boolean {
  return settings.profile_visibility === 'public' || isSelfProfile(settings, viewerUsername)
}

export function publicProfile(settings: UserSettings, viewerUsername?: string): PublicProfile {
  return {
    nickname: settings.nickname,
    display_name: settings.display_name,
    avatar_url: settings.avatar_url,
    bio: settings.bio,
    profile_visibility: settings.profile_visibility,
    public_training_summary_enabled: settings.public_training_summary_enabled,
    is_self: isSelfProfile(settings, viewerUsername),
    tags: (settings.tags || []).filter((t) => t.approved).map((t) => t.tag),
  }
}

export function mappedPkForSettings(settings: UserSettings): string {
  return settings.mapped_pk || settings.pk
}

export function invalidateCache(discordUsername: string): void {
  cache.delete(usernameKey(discordUsername))
}

export async function getSettings(discordUsername: string): Promise<UserSettings | null> {
  const key = usernameKey(discordUsername)
  const cached = cache.get(key)
  if (cached && cached.expires > Date.now()) return cached.settings

  const result = await invokeLambda('pod_user', { function: 'settings_get',  username: discordUsername })
  if (!result) return null
  const settings = normalizeSettings(result as Record<string, unknown>)
  cache.set(key, { settings, expires: Date.now() + CACHE_TTL_MS })
  return settings
}

export async function getSettingsByMappedPk(mappedPk: string): Promise<UserSettings | null> {
  const key = `mapped:${mappedPk}`
  const cached = cache.get(key)
  if (cached && cached.expires > Date.now()) return cached.settings

  const result = await invokeLambda('pod_user', { function: 'settings_get',  mapped_pk: mappedPk })
  if (!result) return null
  const settings = normalizeSettings(result as Record<string, unknown>)
  cache.set(key, { settings, expires: Date.now() + CACHE_TTL_MS })
  return settings
}

export async function updateNickname(discordUsername: string, nickname: string): Promise<UserSettings> {
  if (!validateNickname(nickname)) {
    throw new Error('Invalid nickname: must be 2-32 chars, lowercase alphanumeric, hyphens, underscores only')
  }

  const result = await invokeLambda('pod_user', { function: 'settings_update_nickname',  username: discordUsername, nickname })
  invalidateCache(discordUsername)
  return normalizeSettings(result as Record<string, unknown>)
}

export async function updateProfile(
  discordUsername: string,
  input: {
    profile_visibility?: ProfileVisibility
    display_name?: string
    bio?: string
    public_training_summary_enabled?: boolean
  },
): Promise<UserSettings> {
  const result = await invokeLambda('pod_user', { function: 'settings_update_profile', 
    username: discordUsername,
    profile_visibility: input.profile_visibility,
    display_name: input.display_name,
    bio: input.bio,
    public_training_summary_enabled: input.public_training_summary_enabled,
  })
  invalidateCache(discordUsername)
  return normalizeSettings(result as Record<string, unknown>)
}

export async function updateRankingLocation(
  discordUsername: string,
  input: { ranking_country: string | null; ranking_region: string | null },
): Promise<UserSettings> {
  const result = await invokeLambda('pod_user', { function: 'settings_update_ranking_location', 
    username: discordUsername,
    ranking_country: input.ranking_country,
    ranking_region: input.ranking_region,
  })
  invalidateCache(discordUsername)
  return normalizeSettings(result as Record<string, unknown>)
}

export async function updateAgeClass(
  discordUsername: string,
  input: { age_class: AgeCategory | null },
): Promise<UserSettings> {
  const result = await invokeLambda('pod_user', { function: 'settings_update_age_class', 
    username: discordUsername,
    age_class: input.age_class,
  })
  invalidateCache(discordUsername)
  return normalizeSettings(result as Record<string, unknown>)
}


export async function addTag(discordUsername: string, tag: string): Promise<UserSettings> {
  const result = await invokeLambda('pod_user', { function: 'settings_tag_add',
    username: discordUsername,
    tag,
  })
  invalidateCache(discordUsername)
  return normalizeSettings(result as Record<string, unknown>)
}

export async function removeTag(discordUsername: string, tag: string): Promise<UserSettings> {
  const result = await invokeLambda('pod_user', { function: 'settings_tag_remove',
    username: discordUsername,
    tag,
  })
  invalidateCache(discordUsername)
  return normalizeSettings(result as Record<string, unknown>)
}

export async function approveTag(discordUsername: string, tag: string): Promise<UserSettings> {
  const result = await invokeLambda('pod_user', { function: 'settings_tag_approve',
    username: discordUsername,
    tag,
  })
  invalidateCache(discordUsername)
  return normalizeSettings(result as Record<string, unknown>)
}

export async function proposeTag(
  proposerUsername: string,
  targetNickname: string,
  tag: string,
): Promise<UserSettings> {
  const result = await invokeLambda('pod_user', { function: 'settings_tag_propose',
    proposed_by: proposerUsername,
    target_nickname: targetNickname,
    tag,
  })
  return normalizeSettings(result as Record<string, unknown>)
}

// The initial user row is created on first Discord login via the Fission
// `settings_create` tool (conditional put with attribute_not_exists(pk) + race
// re-get). getSettings() above already routes to `settings_get`; this path was
// the only remaining direct DynamoDB touch for user settings — now removed.
export async function getOrCreateSettings(
  discordId: string,
  discordUsername: string,
  avatarUrl: string | null,
): Promise<UserSettings> {
  const existing = await getSettings(discordUsername)
  if (existing) return existing

  const result = (await invokeLambda('pod_user', { function: 'settings_create', 
    discord_id: discordId,
    discord_username: discordUsername,
    avatar_url: avatarUrl,
  })) as { settings: Record<string, unknown>; created: boolean }

  const settings = normalizeSettings(result.settings)
  cache.set(usernameKey(discordUsername), { settings, expires: Date.now() + CACHE_TTL_MS })

  if (result.created) {
    seedMasterCopiesForNewUser(mappedPkForSettings(settings)).catch((err) => {
      console.error('[userSettings] Failed to seed master copies for new user', settings.username, err)
    })
  }

  return settings
}

export async function resolveMappedPk(
  discordId: string,
  discordUsername: string,
  avatarUrl: string | null,
): Promise<string> {
  const settings = await getOrCreateSettings(discordId, discordUsername, avatarUrl)
  return mappedPkForSettings(settings)
}

// =============================================================================
// Epic 3 — Onboarding helpers + write paths
// =============================================================================

export interface OnboardingStatus {
  is_onboarded: boolean
  next_step: 'role' | 'profile' | 'athlete_basics' | 'done' | null
  state: {
    roles: Role[]
    active_role: Role
    athlete_basics_complete: boolean
    profile_complete: boolean
  }
  has_athlete_basics: boolean
}

export function deriveOnboardingStatus(settings: UserSettings): OnboardingStatus {
  const roles = settings.roles
  const state = {
    roles,
    active_role: settings.active_role,
    athlete_basics_complete: settings.athlete_basics_complete,
    profile_complete: settings.profile_complete,
  }
  const has_athlete_basics = Boolean(
    settings.training_maxes &&
      settings.bodyweight_kg !== null &&
      settings.sex !== null
  )
  let next_step: OnboardingStatus['next_step']
  if (roles.length === 0) {
    next_step = 'role'
  } else if (!settings.profile_complete) {
    next_step = 'profile'
  } else if (roles.includes('athlete') && !has_athlete_basics) {
    next_step = 'athlete_basics'
  } else {
    next_step = 'done'
  }
  return {
    is_onboarded: next_step === 'done',
    next_step,
    state,
    has_athlete_basics,
  }
}

export class ValidationError extends Error {
  status = 400
  constructor(message: string) {
    super(message)
    this.name = 'ValidationError'
  }
}

export interface UpdateAthleteBasicsInput {
  sex: 'male' | 'female'
  country: string
  region: string | null
  bodyweight_kg: number
  training_maxes: TrainingMaxes
}

const MIN_BODYWEIGHT_KG = 30
const MAX_BODYWEIGHT_KG = 300
const MIN_LIFT_KG = 20
const MAX_LIFT_KG = 600

function validateAthleteBasics(input: unknown): UpdateAthleteBasicsInput {
  if (!input || typeof input !== 'object') {
    throw new ValidationError('Body must be a JSON object')
  }
  const obj = input as Record<string, unknown>
  if (obj.sex !== 'male' && obj.sex !== 'female') {
    throw new ValidationError("sex must be 'male' or 'female'")
  }
  if (typeof obj.country !== 'string' || !obj.country.trim()) {
    throw new ValidationError('country is required')
  }
  const country = obj.country.trim().toUpperCase().slice(0, 8)
  if (!country) {
    throw new ValidationError('country is required')
  }
  const regionRaw = obj.region
  const region =
    regionRaw === null || regionRaw === undefined
      ? null
      : typeof regionRaw === 'string'
        ? regionRaw.trim().slice(0, 64) || null
        : (() => {
            throw new ValidationError('region must be a string or null')
          })()
  const bw = normalizePositiveNumber(obj.bodyweight_kg)
  if (bw === null || bw < MIN_BODYWEIGHT_KG || bw > MAX_BODYWEIGHT_KG) {
    throw new ValidationError(
      `bodyweight_kg must be between ${MIN_BODYWEIGHT_KG} and ${MAX_BODYWEIGHT_KG}`,
    )
  }
  if (!obj.training_maxes || typeof obj.training_maxes !== 'object') {
    throw new ValidationError('training_maxes is required')
  }
  const tm = obj.training_maxes as Record<string, unknown>
  const squat = normalizePositiveNumber(tm.squat_kg)
  const bench = normalizePositiveNumber(tm.bench_kg)
  const deadlift = normalizePositiveNumber(tm.deadlift_kg)
  if (squat === null || squat < MIN_LIFT_KG || squat > MAX_LIFT_KG) {
    throw new ValidationError(`squat_kg must be between ${MIN_LIFT_KG} and ${MAX_LIFT_KG}`)
  }
  if (bench === null || bench < MIN_LIFT_KG || bench > MAX_LIFT_KG) {
    throw new ValidationError(`bench_kg must be between ${MIN_LIFT_KG} and ${MAX_LIFT_KG}`)
  }
  if (deadlift === null || deadlift < MIN_LIFT_KG || deadlift > MAX_LIFT_KG) {
    throw new ValidationError(`deadlift_kg must be between ${MIN_LIFT_KG} and ${MAX_LIFT_KG}`)
  }
  return {
    sex: obj.sex,
    country,
    region,
    bodyweight_kg: bw,
    training_maxes: { squat_kg: squat, bench_kg: bench, deadlift_kg: deadlift },
  }
}

export async function updateAthleteBasics(
  discordUsername: string,
  input: unknown,
): Promise<UserSettings> {
  const validated = validateAthleteBasics(input)
  const result = await invokeLambda('pod_user', {
    function: 'settings_update_athlete_basics',
    username: discordUsername,
    input: validated,
  })
  invalidateCache(discordUsername)
  return normalizeSettings(result as Record<string, unknown>)
}

export interface UpdateOnboardingProfileInput {
  display_name: string
  bio?: string
  profile_visibility?: 'private' | 'public'
  public_training_summary_enabled?: boolean
  federations?: string[]
}

function validateOnboardingProfile(input: unknown): UpdateOnboardingProfileInput {
  if (!input || typeof input !== 'object') {
    throw new ValidationError('Body must be a JSON object')
  }
  const obj = input as Record<string, unknown>
  if (typeof obj.display_name !== 'string' || !obj.display_name.trim()) {
    throw new ValidationError('display_name is required')
  }
  const display_name = obj.display_name.trim().slice(0, 80)
  if (!display_name) {
    throw new ValidationError('display_name is required')
  }
  const bio = typeof obj.bio === 'string' ? obj.bio.slice(0, 280) : ''
  const visibility = obj.profile_visibility
  const profile_visibility: 'private' | 'public' =
    visibility === 'public' ? 'public' : 'private'
  const summary = obj.public_training_summary_enabled === true
  let federations: string[] | undefined
  if (obj.federations !== undefined) {
    if (!Array.isArray(obj.federations)) {
      throw new ValidationError('federations must be an array of strings')
    }
    const seen: string[] = []
    for (const item of obj.federations) {
      if (typeof item !== 'string') {
        throw new ValidationError('federations items must be strings')
      }
      const v = item.trim()
      if (v && !seen.includes(v)) seen.push(v)
      if (seen.length >= 20) break
    }
    federations = seen
  }
  return {
    display_name,
    bio,
    profile_visibility,
    public_training_summary_enabled: summary,
    ...(federations !== undefined ? { federations } : {}),
  }
}

export async function updateOnboardingProfile(
  discordUsername: string,
  input: unknown,
): Promise<UserSettings> {
  const validated = validateOnboardingProfile(input)
  const result = await invokeLambda('pod_user', {
    function: 'settings_update_onboarding_profile',
    username: discordUsername,
    input: validated,
  })
  invalidateCache(discordUsername)
  return normalizeSettings(result as Record<string, unknown>)
}

function validateRoles(input: unknown): Role[] {
  if (!Array.isArray(input) || input.length === 0) {
    throw new ValidationError('roles must be a non-empty array')
  }
  const seen: Role[] = []
  for (const item of input) {
    const role = normalizeRole(item)
    if (!role) {
      throw new ValidationError(`Unknown role: ${String(item)}`)
    }
    if (!seen.includes(role)) seen.push(role)
  }
  if (seen.length === 0) {
    throw new ValidationError('At least one role is required')
  }
  return seen
}

export interface UpdateRoleInput {
  roles: Role[]
  active_role?: Role
}

function validateRoleInput(input: unknown): UpdateRoleInput {
  if (!input || typeof input !== 'object') {
    throw new ValidationError('Body must be a JSON object')
  }
  const obj = input as Record<string, unknown>
  const roles = validateRoles(obj.roles)
  let active_role: Role | undefined
  if (obj.active_role !== undefined) {
    const ar = normalizeRole(obj.active_role)
    if (!ar) {
      throw new ValidationError(`Unknown active_role: ${String(obj.active_role)}`)
    }
    if (!roles.includes(ar)) {
      throw new ValidationError('active_role must be one of the assigned roles')
    }
    active_role = ar
  }
  return { roles, ...(active_role ? { active_role } : {}) }
}

export async function updateRole(
  discordUsername: string,
  input: unknown,
): Promise<UserSettings> {
  const validated = validateRoleInput(input)
  const result = await invokeLambda('pod_user', {
    function: 'settings_update_role',
    username: discordUsername,
    ...validated,
  })
  invalidateCache(discordUsername)
  return normalizeSettings(result as Record<string, unknown>)
}
