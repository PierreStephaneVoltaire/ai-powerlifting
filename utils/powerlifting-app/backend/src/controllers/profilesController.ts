import { Request, Response } from 'express'
import { getProfileByNickname, searchProfiles } from '../services/userSettings'
import { AppError } from '../middleware/errorHandler'

export async function searchProfilesHandler(req: Request, res: Response): Promise<void> {
  const query = typeof req.query.q === 'string' ? req.query.q : ''
  const profiles = await searchProfiles(query, req.user?.username)
  res.json({ data: profiles, error: null })
}

export async function getProfileHandler(req: Request, res: Response): Promise<void> {
  const profile = await getProfileByNickname(req.params.nickname, req.user?.username)
  if (!profile) {
    throw new AppError('Profile not found', 404)
  }

  res.json({ data: profile, error: null })
}
