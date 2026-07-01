import { Request, Response } from 'express'
import {
  getSettings,
  getSettingsByMappedPk,
  updateNickname,
  updateProfile,
  updateRankingLocation,
  updateAgeClass,
  validateNickname,
  invalidateCache,
  type ProfileVisibility,
} from '../services/userSettings'
import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'

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

export async function updateAvatarHandler(req: Request, res: Response): Promise<void> {
  if (!req.user) {
    throw new AppError('Not authenticated', 401, 'AUTH_REQUIRED')
  }

  const file = req.file
  if (!file) {
    throw new AppError('No profile picture provided', 400)
  }

  const fileB64 = Buffer.from(file.buffer).toString('base64')
  const settings = await invokeLambda('settings_update_avatar', {
    username: req.user.username,
    mapped_pk: req.mapped_pk,
    file_b64: fileB64,
    mimetype: file.mimetype,
    filename: file.originalname,
  })

  invalidateCache(req.user.username)
  res.json({ data: settings })
}
