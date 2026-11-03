import { AsyncLocalStorage } from 'async_hooks'

export interface OperationContext {
  athlete: string
  person: string
  ifJobId?: string
  identity?: { issuer: string; provider: 'authentik' | 'discord'; sub: string; discord_subjects?: string[] }
}

export const operationScope = new AsyncLocalStorage<OperationContext>()
