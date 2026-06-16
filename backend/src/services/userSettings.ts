import { GetCommand, PutCommand, ScanCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, USER_TABLE } from '../db/dynamo'
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
    ranking_country: typeof raw.ranking_country === 'string' && raw.ranking_country.trim() ? raw.ranking_country.trim() : null,
    ranking_region: typeof raw.ranking_region === 'string' && raw.ranking_region.trim() ? raw.ranking_region.trim() : null,
    age_class: normalizeAgeClass(raw.age_class),
    created_at: String(raw.created_at || new Date().toISOString()),
    updated_at: String(raw.updated_at || new Date().toISOString()),
  }
}

function isSelfProfile(settings: UserSettings, viewerUsername?: string): boolean {
  const viewerKey = viewerUsername ? usernameKey(viewerUsername) : ''
  return Boolean(viewerKey && viewerKey === settingsUsernameKey(settings))
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
  }
}

export async function getSettings(discordUsername: string): Promise<UserSettings | null> {
  const key = usernameKey(discordUsername)
  const cached = cache.get(key)
  if (cached && cached.expires > Date.now()) return cached.settings

  const result = await docClient.send(new GetCommand({
    TableName: USER_TABLE,
    Key: { pk: key },
  }))

  if (!result.Item) return null

  const settings = normalizeSettings(result.Item as Record<string, unknown>)
  cache.set(key, { settings, expires: Date.now() + CACHE_TTL_MS })
  return settings
}

export async function getOrCreateSettings(
  discordId: string,
  discordUsername: string,
  avatarUrl: string | null,
): Promise<UserSettings> {
  const existing = await getSettings(discordUsername)
  if (existing) return existing

  const now = new Date().toISOString()
  const username = usernameKey(discordUsername)
  const settings: UserSettings = {
    pk: username,
    username,
    discord_id: discordId,
    discord_username: discordUsername,
    avatar_url: avatarUrl,
    nickname: username,
    profile_visibility: 'private',
    display_name: discordUsername,
    bio: '',
    public_training_summary_enabled: false,
    ranking_country: null,
    ranking_region: null,
    age_class: 'open',
    created_at: now,
    updated_at: now,
  }

  let created = true
  await docClient.send(new PutCommand({
    TableName: USER_TABLE,
    Item: settings,
    ConditionExpression: 'attribute_not_exists(pk)',
  })).catch(() => {
    // Race: another request created it first. Fetch instead.
    created = false
  })

  if (!created) {
    const raced = await getSettings(discordUsername)
    if (raced) return raced
  }

  cache.set(usernameKey(discordUsername), { settings, expires: Date.now() + CACHE_TTL_MS })

  // Fire-and-forget: seed master comp + fed copies for the new user
  seedMasterCopiesForNewUser(mappedPkForSettings(settings)).catch((err) => {
    console.error('[userSettings] Failed to seed master copies for new user', username, err)
  })

  return settings
}

export function mappedPkForSettings(settings: UserSettings): string {
  return settings.mapped_pk || settings.pk
}

export async function resolveMappedPk(
  discordId: string,
  discordUsername: string,
  avatarUrl: string | null,
): Promise<string> {
  const settings = await getOrCreateSettings(discordId, discordUsername, avatarUrl)
  return mappedPkForSettings(settings)
}

export async function updateNickname(discordUsername: string, nickname: string): Promise<UserSettings> {
  if (!validateNickname(nickname)) {
    throw new Error('Invalid nickname: must be 2-32 chars, lowercase alphanumeric, hyphens, underscores only')
  }

  const existing = await getSettings(discordUsername)
  if (!existing) {
    throw new Error('Settings not found')
  }

  const now = new Date().toISOString()
  await docClient.send(new UpdateCommand({
    TableName: USER_TABLE,
    Key: { pk: existing.pk },
    UpdateExpression: 'SET #nick = :nick, updated_at = :now',
    ConditionExpression: 'attribute_exists(pk)',
    ExpressionAttributeNames: { '#nick': 'nickname' },
    ExpressionAttributeValues: { ':nick': nickname, ':now': now },
  }))

  cache.delete(usernameKey(discordUsername))
  return getSettings(discordUsername) as Promise<UserSettings>
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
  const existing = await getSettings(discordUsername)
  if (!existing) {
    throw new Error('Settings not found')
  }

  const profileVisibility = input.profile_visibility ?? existing.profile_visibility
  const displayName = input.display_name === undefined
    ? existing.display_name
    : normalizeDisplayName(input.display_name, existing.discord_username || existing.nickname)
  const bio = input.bio === undefined ? existing.bio : normalizeBio(input.bio)
  const publicTrainingSummaryEnabled = input.public_training_summary_enabled
    ?? existing.public_training_summary_enabled
  const now = new Date().toISOString()

  await docClient.send(new UpdateCommand({
    TableName: USER_TABLE,
    Key: { pk: existing.pk },
    UpdateExpression: [
      'SET profile_visibility = :visibility',
      'display_name = :display',
      'bio = :bio',
      'public_training_summary_enabled = :summary',
      'updated_at = :now',
    ].join(', '),
    ConditionExpression: 'attribute_exists(pk)',
    ExpressionAttributeValues: {
      ':visibility': profileVisibility,
      ':display': displayName,
      ':bio': bio,
      ':summary': publicTrainingSummaryEnabled,
      ':now': now,
    },
  }))

  cache.delete(usernameKey(discordUsername))
  return getSettings(discordUsername) as Promise<UserSettings>
}

export async function updateAvatarUrl(discordUsername: string, avatarUrl: string | null): Promise<UserSettings> {
  const existing = await getSettings(discordUsername)
  if (!existing) {
    throw new Error('Settings not found')
  }

  const now = new Date().toISOString()
  await docClient.send(new UpdateCommand({
    TableName: USER_TABLE,
    Key: { pk: existing.pk },
    UpdateExpression: 'SET avatar_url = :avatar, updated_at = :now',
    ConditionExpression: 'attribute_exists(pk)',
    ExpressionAttributeValues: {
      ':avatar': avatarUrl,
      ':now': now,
    },
  }))

  cache.delete(usernameKey(discordUsername))
  return getSettings(discordUsername) as Promise<UserSettings>
}

async function scanSettings(): Promise<UserSettings[]> {
  const settings: UserSettings[] = []
  let ExclusiveStartKey: Record<string, unknown> | undefined

  do {
    const result = await docClient.send(new ScanCommand({
      TableName: USER_TABLE,
      ExclusiveStartKey,
    }))

    for (const item of result.Items || []) {
      settings.push(normalizeSettings(item as Record<string, unknown>))
    }

    ExclusiveStartKey = result.LastEvaluatedKey as Record<string, unknown> | undefined
  } while (ExclusiveStartKey)

  return settings
}

export async function searchProfiles(query: string, viewerUsername?: string): Promise<PublicProfile[]> {
  const normalizedQuery = query.trim().toLowerCase()
  const allSettings = await scanSettings()

  return allSettings
    .filter((settings) => {
      if (!canViewProfile(settings, viewerUsername)) return false
      if (!normalizedQuery) return true
      return [
        settings.nickname,
        settings.display_name,
        settings.discord_username,
        settings.bio,
      ].some((value) => value.toLowerCase().includes(normalizedQuery))
    })
    .sort((a, b) => a.display_name.localeCompare(b.display_name))
    .slice(0, 50)
    .map((settings) => publicProfile(settings, viewerUsername))
}

export async function getProfileSettingsByNickname(nickname: string, viewerUsername?: string): Promise<UserSettings | null> {
  const normalizedNickname = nickname.trim().toLowerCase()
  if (!validateNickname(normalizedNickname)) return null

  const allSettings = await scanSettings()
  const settings = allSettings.find((item) => item.nickname === normalizedNickname)
  if (!settings) return null

  if (!canViewProfile(settings, viewerUsername)) return null
  return settings
}

export async function getProfileSettingsByMappedPk(mappedPk: string, viewerUsername?: string): Promise<UserSettings | null> {
  const target = mappedPk.trim()
  if (!target || !validateMappedPk(target)) return null

  const allSettings = await scanSettings()
  const candidates = allSettings
    .filter((settings) => mappedPkForSettings(settings) === target || settings.pk === target)
    .filter((settings) => canViewProfile(settings, viewerUsername))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))

  return candidates.find((settings) => isSelfProfile(settings, viewerUsername)) ?? candidates[0] ?? null
}

export async function getProfileByNickname(nickname: string, viewerUsername?: string): Promise<PublicProfile | null> {
  const settings = await getProfileSettingsByNickname(nickname, viewerUsername)
  return settings ? publicProfile(settings, viewerUsername) : null
}

export function invalidateCache(discordUsername: string): void {
  cache.delete(usernameKey(discordUsername))
}

export async function updateRankingLocation(
  discordUsername: string,
  input: { ranking_country: string | null; ranking_region: string | null },
): Promise<UserSettings> {
  const existing = await getSettings(discordUsername)
  if (!existing) {
    throw new Error('Settings not found')
  }

  const rankingCountry = typeof input.ranking_country === 'string' && input.ranking_country.trim()
    ? input.ranking_country.trim()
    : null
  const rankingRegion = typeof input.ranking_region === 'string' && input.ranking_region.trim()
    ? input.ranking_region.trim()
    : null
  const now = new Date().toISOString()

  await docClient.send(new UpdateCommand({
    TableName: USER_TABLE,
    Key: { pk: existing.pk },
    UpdateExpression: 'SET ranking_country = :country, ranking_region = :region, updated_at = :now',
    ConditionExpression: 'attribute_exists(pk)',
    ExpressionAttributeValues: {
      ':country': rankingCountry,
      ':region': rankingRegion,
      ':now': now,
    },
  }))

  cache.delete(usernameKey(discordUsername))
  return getSettings(discordUsername) as Promise<UserSettings>
}

export async function updateAgeClass(
  discordUsername: string,
  input: { age_class: AgeCategory | null },
): Promise<UserSettings> {
  const existing = await getSettings(discordUsername)
  if (!existing) {
    throw new Error('Settings not found')
  }

  const ageClass = typeof input.age_class === 'string' && AGE_CATEGORY_VALUES.includes(input.age_class as AgeCategory)
    ? (input.age_class as AgeCategory)
    : 'open'
  const now = new Date().toISOString()

  await docClient.send(new UpdateCommand({
    TableName: USER_TABLE,
    Key: { pk: existing.pk },
    UpdateExpression: 'SET age_class = :age, updated_at = :now',
    ConditionExpression: 'attribute_exists(pk)',
    ExpressionAttributeValues: {
      ':age': ageClass,
      ':now': now,
    },
  }))

  cache.delete(usernameKey(discordUsername))
  return getSettings(discordUsername) as Promise<UserSettings>
}
