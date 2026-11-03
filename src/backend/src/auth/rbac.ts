import type { Request } from 'express'
import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'
import type { Scope, Access } from './scopes'
import type { AccessContext } from '@powerlifting/types'
export type { AccessContext } from '@powerlifting/types'

export async function evaluateRbac(_req: Request): Promise<AccessContext> {
  return invokeLambda('access_context', {})
}

export async function authorizeScope(req: Request, scope: Scope, access: Access): Promise<AccessContext> {
  const context = await evaluateRbac(req)
  if (!context.permissions.includes(`${scope}:${access}`)) throw new AppError('Not permitted', req.user ? 403 : 401, 'NOT_PERMITTED')
  req.readOnly = !context.permissions.includes(`${scope}:write`)
  return context
}
