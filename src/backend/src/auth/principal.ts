import type { OperationContext } from '../utils/operationScope'
import { securityRequest } from './security'

export async function principalToken(operation: string, context: OperationContext, destination: string): Promise<string> {
  const result = await securityRequest<{ principal: string }>('/v1/principals', {
    identity_token: context.identityToken,
    principal: context.principal,
    athlete: context.athlete,
    operation,
    destination,
  })
  if (typeof result.principal !== 'string' || !result.principal) throw new Error('Principal issuance failed')
  return result.principal
}

export async function serviceHeaders(operation: string, context: OperationContext, destination: string): Promise<Record<string, string>> {
  return {
    'Content-Type': 'application/json',
    'X-Person-Pk': context.person,
    'X-Athlete-Pk': context.athlete,
    'X-PL-Principal': await principalToken(operation, context, destination),
  }
}
