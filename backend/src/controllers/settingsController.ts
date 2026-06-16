import { Request, Response } from 'express'
import { DeleteObjectCommand, S3Client } from '@aws-sdk/client-s3'
import { Upload } from '@aws-sdk/lib-storage'
import { v4 as uuidv4 } from 'uuid'
import {
  getSettings,
  getSettingsByMappedPk,
  updateNickname,
  updateAvatarUrl,
  updateProfile,
  updateRankingLocation,
  updateAgeClass,
  validateNickname,
  invalidateCache,
  type ProfileVisibility,
} from '../services/userSettings'
import { AppError } from '../middleware/errorHandler'
import { getProxyUrl } from '../services/sessionStore'

const S3_BUCKET = process.env.VIDEOS_BUCKET || 'powerlifting-session-videos'
const S3_REGION = process.env.AWS_REGION || 'ca-central-1'

const s3Client = new S3Client({
  region: S3_REGION,
  credentials: process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? {
        accessKeyId: process.env.AWS_ACCESS_KEY_ID,
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      }
    : undefined,
})

function avatarExtension(file: Express.Multer.File): string {
  const byMime: Record<string, string> = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/gif': 'gif',
  }
  const mimeExtension = byMime[file.mimetype]
  if (mimeExtension) return mimeExtension
  return file.originalname.split('.').pop()?.toLowerCase() || 'jpg'
}

function profileAvatarKeyFromUrl(value: string | null | undefined): string | null {
  if (!value) return null
  const prefix = '/api/videos/media/'
  if (!value.startsWith(`${prefix}profiles/`)) return null
  return decodeURIComponent(value.slice(prefix.length))
}

function s3SafeSegment(value: string): string {
  return value.replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 128) || 'user'
}

export async function getSettingsHandler(req: Request, res: Response): Promise<void> {

  let settings = null
  if (req.user?.username) {
    settings = await getSettings(req.user.username)
  }
  if (!settings && req.mapped_pk) {
    settings = await getSettingsByMappedPk(req.mapped_pk)
  }
  if (!settings) {

    if (!req.user) {
      res.json({
        data: {
          pk: 'operator',
          username: 'operator',
          discord_id: '',
          discord_username: 'operator',
          avatar_url: null,
          nickname: 'operator',
          profile_visibility: 'private',
          display_name: 'operator',
          bio: '',
          public_training_summary_enabled: false,
          ranking_country: null,
          ranking_region: null,
          age_class: 'open',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      })
      return
    }
    throw new AppError('Settings not found', 404)
  }

  res.json({ data: settings })
}

export async function updateNicknameHandler(req: Request, res: Response): Promise<void> {
  if (!req.user) {
    throw new AppError('Not authenticated', 401)
  }

  const { nickname } = req.body
  if (typeof nickname !== 'string' || !validateNickname(nickname)) {
    throw new AppError('Invalid nickname: must be 2-32 chars, lowercase alphanumeric, hyphens, underscores only', 400)
  }

  const settings = await updateNickname(req.user.username, nickname)
  invalidateCache(req.user.username)
  res.json({ data: settings })
}

export async function updateProfileHandler(req: Request, res: Response): Promise<void> {
  if (!req.user) {
    throw new AppError('Not authenticated', 401, 'AUTH_REQUIRED')
  }

  const { profile_visibility, display_name, bio, public_training_summary_enabled } = req.body
  if (profile_visibility !== undefined && profile_visibility !== 'private' && profile_visibility !== 'public') {
    throw new AppError('profile_visibility must be private or public', 400)
  }
  if (display_name !== undefined && typeof display_name !== 'string') {
    throw new AppError('display_name must be a string', 400)
  }
  if (bio !== undefined && typeof bio !== 'string') {
    throw new AppError('bio must be a string', 400)
  }
  if (
    public_training_summary_enabled !== undefined &&
    typeof public_training_summary_enabled !== 'boolean'
  ) {
    throw new AppError('public_training_summary_enabled must be a boolean', 400)
  }

  const settings = await updateProfile(req.user.username, {
    profile_visibility: profile_visibility as ProfileVisibility | undefined,
    display_name,
    bio,
    public_training_summary_enabled,
  })
  res.json({ data: settings })
}

export async function updateAvatarHandler(req: Request, res: Response): Promise<void> {
  if (!req.user) {
    throw new AppError('Not authenticated', 401, 'AUTH_REQUIRED')
  }

  const file = req.file
  if (!file) {
    throw new AppError('No profile picture provided', 400)
  }

  const existing = await getSettings(req.user.username)
  if (!existing) {
    throw new AppError('Settings not found', 404)
  }

  const avatarId = uuidv4()
  const extension = avatarExtension(file)
  const owner = s3SafeSegment(req.mapped_pk || existing.pk)
  const s3Key = `profiles/${owner}/avatars/${avatarId}.${extension}`

  try {
    await new Upload({
      client: s3Client,
      params: {
        Bucket: S3_BUCKET,
        Key: s3Key,
        Body: file.buffer,
        ContentType: file.mimetype,
        Metadata: {
          profile_avatar: 'true',
          username: existing.username,
          mapped_pk: owner,
        },
      },
    }).done()
  } catch (err) {
    console.error('[SettingsController] S3 avatar upload failed:', err)
    throw new AppError('Failed to upload profile picture', 500)
  }

  const avatarUrl = getProxyUrl(s3Key)
  const settings = await updateAvatarUrl(req.user.username, avatarUrl)
  const previousKey = profileAvatarKeyFromUrl(existing.avatar_url)
  if (previousKey && previousKey !== s3Key) {
    s3Client.send(new DeleteObjectCommand({ Bucket: S3_BUCKET, Key: previousKey })).catch((err) => {
      console.warn('[SettingsController] Failed to delete previous avatar:', err)
    })
  }

  res.json({ data: settings })
}

export async function updateRankingLocationHandler(req: Request, res: Response): Promise<void> {
  if (!req.user) {
    throw new AppError('Not authenticated', 401, 'AUTH_REQUIRED')
  }

  const { ranking_country, ranking_region } = req.body
  if (ranking_country !== undefined && ranking_country !== null && typeof ranking_country !== 'string') {
    throw new AppError('ranking_country must be a string or null', 400)
  }
  if (ranking_region !== undefined && ranking_region !== null && typeof ranking_region !== 'string') {
    throw new AppError('ranking_region must be a string or null', 400)
  }

  const settings = await updateRankingLocation(req.user.username, {
    ranking_country: ranking_country ?? null,
    ranking_region: ranking_region ?? null,
  })
  res.json({ data: settings })
}

export async function updateAgeClassHandler(req: Request, res: Response): Promise<void> {
  if (!req.user) {
    throw new AppError('Not authenticated', 401, 'AUTH_REQUIRED')
  }

  const { age_class } = req.body
  if (age_class !== undefined && age_class !== null && typeof age_class !== 'string') {
    throw new AppError('age_class must be a string or null', 400)
  }

  const settings = await updateAgeClass(req.user.username, {
    age_class: typeof age_class === 'string' ? (age_class as never) : null,
  })
  res.json({ data: settings })
}

