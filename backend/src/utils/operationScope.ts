import { AsyncLocalStorage } from 'async_hooks'

export const operationScope = new AsyncLocalStorage<{ athlete: string; person: string; ifJobId?: string }>()
