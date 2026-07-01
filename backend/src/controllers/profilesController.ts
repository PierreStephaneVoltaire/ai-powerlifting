import { Request, Response } from 'express'
import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'

export async function searchProfilesHandler(req: Request, res: Response): Promise<void> {
  const query = typeof req.query.q === 'string' ? req.query.q : ''
  const result = await invokeLambda('profile_search', {
    query,
    viewer_username: req.user?.username,
  })
  res.json({ data: result?.profiles ?? [], error: null })
}

export async function getCurrentProfileHandler(req: Request, res: Response): Promise<void> {
  const profile = await invokeLambda('profile_get_current', {
    mapped_pk: req.mapped_pk ?? 'operator',
    viewer_username: req.user?.username,
  })
  if (!profile) {
    throw new AppError('Profile not found', 404)
  }
  res.json({ data: profile, error: null })
}

export async function getProfileHandler(req: Request, res: Response): Promise<void> {
  const profile = await invokeLambda('profile_get', {
    nickname: req.params.nickname,
    viewer_username: req.user?.username,
  })
  if (!profile) {
    throw new AppError('Profile not found', 404)
  }
  res.json({ data: profile, error: null })
}
