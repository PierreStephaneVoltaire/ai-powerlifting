import { invokeLambda } from '../utils/lambda'
import { seedMasterCopiesForNewUser } from './masterCopy'
import type { AgeCategory } from '@powerlifting/types'

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

function normalizeSettings(raw: Record<string, unknown>): UserSettings {
  const discordUsername = String(raw.discord_username || raw.username || '')
  const username = usernameKey(String(raw.username || discordUsername || raw.nickname || 'user'))
  const nickname = String(raw.nickname || username)
  const pk = String(raw.pk || username)
  const mappedPk = normalizeMappedPk(raw.mapped_pk)
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
