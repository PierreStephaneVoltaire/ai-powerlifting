import { AsyncLocalStorage } from 'async_hooks'
import type { RequestHandler } from 'express'

export interface OperationContext {
  athlete: string
  person: string
  ifJobId?: string
  identityToken?: string
  principal?: string
}

export const operationScope = new AsyncLocalStorage<OperationContext>()

export const restoreOperationScope: RequestHandler = (req, _res, next) => {
  operationScope.run({ athlete: req.mapped_pk || '', person: req.actor_mapped_pk || '', identityToken: req.identityToken, principal: req.operationPrincipal }, next)
}
