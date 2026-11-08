import { AsyncLocalStorage } from 'async_hooks'
import type { RequestHandler } from 'express'

export interface OperationContext {
  athlete: string
  person: string
  ifJobId?: string
  identity?: { issuer: string; provider: 'authentik' | 'discord'; sub: string; discord_subjects?: string[] }
}

export const operationScope = new AsyncLocalStorage<OperationContext>()

export const restoreOperationScope: RequestHandler = (req, _res, next) => {
  operationScope.run({ athlete: req.mapped_pk || '', person: req.actor_mapped_pk || '' }, next)
}
