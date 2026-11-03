import jwt from 'jsonwebtoken'
import type { OperationContext } from '../utils/operationScope'

export function principalToken(operation: string, context: OperationContext): string {
  const secret = process.env.PL_PRINCIPAL_SECRET || ''
  if (secret.length < 32) throw new Error('PL_PRINCIPAL_SECRET must contain at least 32 characters')
  return jwt.sign({ athlete: context.athlete, operation, ...(context.identity ? { identity: context.identity } : {}) }, secret, {
    algorithm: 'HS256', issuer: 'powerlifting-gateway', audience: 'powerlifting-services', subject: context.person, expiresIn: 300,
  })
}
