import { Request, Response } from 'express'
import { AppError } from '../middleware/errorHandler'
import {
  createGrant,
  revokeGrant,
  listGrants,
  checkGrant,
  type CreateGrantInput,
  type RevokeGrantInput,
  type ListGrantsInput,
  type CheckGrantInput,
} from '../services/grants'
import { OPERATOR_MAPPED_PK } from '../auth/identity'

function requireUser(req: Request): void {
  if (!req.user) {
    throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
  }
}

function isGranteeSelfClaimAllowed(req: Request, athleteMappedPk: string): boolean {
  if (!req.user) return false
  if (req.user.actor_mapped_pk === OPERATOR_MAPPED_PK) return true
  if (req.user.actor_mapped_pk === athleteMappedPk) return true
  // Coaches/handlers with an active grants:write grant on the athlete can also
  // issue/revoke grants for that athlete.
  return false
}

export async function createGrantHandler(req: Request, res: Response): Promise<void> {
  requireUser(req)
  const body = req.body as Partial<CreateGrantInput>
  const athleteMappedPk = String(body.athlete_mapped_pk || req.user!.actor_mapped_pk)
  if (!isGranteeSelfClaimAllowed(req, athleteMappedPk) && !req.readOnly) {
    // Re-check: athletes with grants:write can also self-manage.
    if (athleteMappedPk !== req.user!.actor_mapped_pk) {
      const delegated = await checkGrant({
        athlete_mapped_pk: athleteMappedPk,
        actor_mapped_pk: req.user!.actor_mapped_pk,
        grant_type: 'coach',
        scope: 'write',
      })
      const delegated2 = await checkGrant({
        athlete_mapped_pk: athleteMappedPk,
        actor_mapped_pk: req.user!.actor_mapped_pk,
        grant_type: 'handler',
        scope: 'write',
      })
      if (!delegated.allowed && !delegated2.allowed) {
        throw new AppError('Not permitted to grant on this athlete', 403, 'NOT_PERMITTED')
      }
    }
  }
  const grant = await createGrant({
    athlete_mapped_pk: athleteMappedPk,
    grantee_mapped_pk: String(body.grantee_mapped_pk || ''),
    grantee_nickname: body.grantee_nickname,
    grantee_discord_id: body.grantee_discord_id,
    grantee_authentik_sub: body.grantee_authentik_sub,
    grant_type: body.grant_type ?? 'coach',
    scope: body.scope ?? 'read',
    tied_competition_ids: body.tied_competition_ids,
    tied_competition_dates: body.tied_competition_dates,
    note: body.note,
    created_by: req.user!.actor_mapped_pk,
  })
  res.json({ data: grant })
}

export async function revokeGrantHandler(req: Request, res: Response): Promise<void> {
  requireUser(req)
  const body = req.body as Partial<RevokeGrantInput>
  const athleteMappedPk = String(body.athlete_mapped_pk || req.user!.actor_mapped_pk)
  if (athleteMappedPk !== req.user!.actor_mapped_pk) {
    const delegated = await checkGrant({
      athlete_mapped_pk: athleteMappedPk,
      actor_mapped_pk: req.user!.actor_mapped_pk,
      grant_type: 'coach',
      scope: 'write',
    })
    if (!delegated.allowed) {
      throw new AppError('Not permitted to revoke on this athlete', 403, 'NOT_PERMITTED')
    }
  }
  const result = await revokeGrant({
    athlete_mapped_pk: athleteMappedPk,
    sk: String(body.sk || ''),
    revoked_by: req.user!.actor_mapped_pk,
  })
  res.json({ data: result })
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
