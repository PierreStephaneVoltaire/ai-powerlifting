import { invokeLambda } from '../utils/lambda'

export type AnalyticsOperationName =
  | 'analytics.manifest'
  | 'analytics.sections_queue'
  | 'analytics.sections_get'
  | 'analytics.sections_invalidate'
  | 'analytics.weekly'
  | 'analytics.bundle'
  | 'analytics.blocks_list'
  | 'analytics.blocks_get'
  | 'analytics.blocks_regenerate'
  | 'analytics.block_evaluation'
  | 'analytics.correlation'
  | 'analytics.export'
  | 'analytics.compare'
  | 'analytics.compare_ai'
  | 'analytics.regenerate'
  | 'analytics.markdown'

export async function invokeAnalyticsOperation<T>(
  operation: AnalyticsOperationName,
  pk: string,
  arguments_: Record<string, unknown> = {},
): Promise<T> {
  return invokeLambda(operation, { ...arguments_, pk }) as Promise<T>
}
