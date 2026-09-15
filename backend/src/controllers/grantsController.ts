import { Request, Response } from 'express'
import { AppError } from '../middleware/errorHandler'
import {
  listGrants,
  checkGrant,
  type ListGrantsInput,
  type CheckGrantInput,
} from '../services/grants'

function requireUser(req: Request): void {
  if (!req.user) {
    throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
  }
}

export async function listGrantsHandler(req: Request, res: Response): Promise<void> {
  requireUser(req)
  const q = req.query as Record<string, string | undefined>
  const input: ListGrantsInput = {
    athlete_mapped_pk: q.athlete_mapped_pk || req.user!.actor_mapped_pk,
    grantee_mapped_pk: q.grantee_mapped_pk,
    include_inactive: q.include_inactive === 'true',
  }
  if (input.athlete_mapped_pk !== req.user!.actor_mapped_pk) {
    const allowed = await checkGrant({
      athlete_mapped_pk: input.athlete_mapped_pk!,
      actor_mapped_pk: req.user!.actor_mapped_pk,
      grant_type: 'coach',
      scope: 'read',
    })
    if (!allowed.allowed) {
      throw new AppError('Not permitted to list grants for this athlete', 403, 'NOT_PERMITTED')
    }
  }
  const result = await listGrants(input)
  res.json({ data: result })
}

export async function checkGrantHandler(req: Request, res: Response): Promise<void> {
  requireUser(req)
  const q = req.query as Record<string, string | undefined>
  const input: CheckGrantInput = {
    athlete_mapped_pk: q.athlete_mapped_pk || '',
    actor_mapped_pk: q.actor_mapped_pk || req.user!.actor_mapped_pk,
    grant_type: (q.grant_type as 'coach' | 'handler') || undefined,
    scope: (q.scope as 'read' | 'write') || undefined,
    tied_competition_id: q.tied_competition_id,
  }
  const result = await checkGrant(input)
  res.json({ data: result })
}
