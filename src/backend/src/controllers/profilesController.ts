import { Request, Response } from 'express'
import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'

export async function searchProfilesHandler(req: Request, res: Response): Promise<void> {
  const query = typeof req.query.q === 'string' ? req.query.q : ''
  const result = await invokeLambda('pod_user', { function: 'profile_search', 
    query,
    viewer_username: req.actor_mapped_pk || undefined,
    tags: typeof req.query.tag === 'string' ? [req.query.tag] : Array.isArray(req.query.tag) ? req.query.tag : [],
    federations: typeof req.query.federation === 'string' ? [req.query.federation] : Array.isArray(req.query.federation) ? req.query.federation : [],
    tag_mode: req.query.tag_mode || 'and',
    ...(req.query.role ? { role: req.query.role } : {}),
    ...(req.query.cursor ? { cursor: req.query.cursor } : {}),
  })
  res.json({ data: result, error: null })
}

export async function getCurrentProfileHandler(req: Request, res: Response): Promise<void> {
  const profile = await invokeLambda('pod_user', { function: 'profile_get_current', 
    mapped_pk: req.settings?.mapped_pk || req.actor_mapped_pk,
    viewer_username: req.actor_mapped_pk || undefined,
  })
  if (!profile) {
    throw new AppError('Profile not found', 404)
  }
  res.json({ data: profile, error: null })
}

export async function getProfileHandler(req: Request, res: Response): Promise<void> {
  const profile = await invokeLambda('pod_user', { function: 'profile_get', 
    nickname: req.params.nickname,
    viewer_username: req.actor_mapped_pk || undefined,
  })
  if (!profile) {
    throw new AppError('Profile not found', 404)
  }
  res.json({ data: profile, error: null })
}
