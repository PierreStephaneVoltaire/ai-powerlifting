import { callOperation } from '../utils/operations'

export async function requestRelationship(payload: Record<string, unknown>): Promise<unknown> {
  return callOperation('relationship_request', payload)
}

export async function respondRelationship(payload: Record<string, unknown>): Promise<unknown> {
  return callOperation('relationship_respond', payload)
}

export async function revokeRelationship(payload: Record<string, unknown>): Promise<unknown> {
  return callOperation('relationship_revoke', payload)
}

export async function listRelationships(): Promise<unknown> {
  return callOperation('relationship_list', {})
}

export async function relationshipHistory(): Promise<unknown> {
  return callOperation('relationship_history', {})
}

export async function updateFavorite(payload: Record<string, unknown>): Promise<unknown> {
  return callOperation('favorite', payload)
}

export async function listFavorites(): Promise<unknown> {
  return callOperation('favorites', {})
}

export async function listNotifications(): Promise<unknown> {
  return callOperation('notifications', {})
}

export async function readNotifications(payload: Record<string, unknown>): Promise<unknown> {
  return callOperation('notifications_read', payload)
}
