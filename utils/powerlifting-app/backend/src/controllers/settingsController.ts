import { Request, Response } from 'express'
import {
  getSettings,
  updateNickname,
  updateProfile,
  validateNickname,
  invalidateCache,
  type ProfileVisibility,
} from '../services/userSettings'
import { AppError } from '../middleware/errorHandler'

export async function getSettingsHandler(req: Request, res: Response): Promise<void> {
  if (!req.user) {
    throw new AppError('Not authenticated', 401)
  }

  const settings = await getSettings(req.user.username)
  if (!settings) {
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
