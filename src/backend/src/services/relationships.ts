import { invokeLambda } from '../utils/lambda'

export async function requestRelationship(payload: Record<string, unknown>): Promise<unknown> {
  return invokeLambda('relationship_request', payload)
}

export async function respondRelationship(payload: Record<string, unknown>): Promise<unknown> {
  return invokeLambda('relationship_respond', payload)
}

export async function revokeRelationship(payload: Record<string, unknown>): Promise<unknown> {
  return invokeLambda('relationship_revoke', payload)
}

export async function listRelationships(): Promise<unknown> {
  return invokeLambda('relationship_list', {})
}

export async function relationshipHistory(): Promise<unknown> {
  return invokeLambda('relationship_history', {})
}

export async function updateFavorite(payload: Record<string, unknown>): Promise<unknown> {
  return invokeLambda('favorite', payload)
}

export async function listFavorites(): Promise<unknown> {
  return invokeLambda('favorites', {})
}

export async function listNotifications(): Promise<unknown> {
  return invokeLambda('notifications', {})
}

export async function readNotifications(payload: Record<string, unknown>): Promise<unknown> {
  return invokeLambda('notifications_read', payload)
}
