import api from './http'
import type { ApiResponse } from '@powerlifting/types'

export interface RelationshipRequest {
  relationship_id: string
  state: string
  active?: boolean
  legacy_relationship?: boolean
  athlete_display_name?: string
  athlete_mapped_pk: string
  athlete_person_pk: string
  requester_person_pk?: string
  recipient_person_pk: string
  request_direction?: 'athlete_to_delegate' | 'coach_to_athlete'
  relationship_type: 'coach' | 'handler' | 'peer'
  permissions: string[]
  tied_competition_ids: string[]
  expires_at: string
  scope?: 'read' | 'write'
  replace_current_relationship_id?: string
  note?: string
  created_at: string
}

function mutationKey(): string {
  return crypto.randomUUID()
}

export function listRelationshipsApi(): Promise<{ sent: RelationshipRequest[]; received: RelationshipRequest[]; history: RelationshipRequest[] }> {
  return api.get<ApiResponse<{ sent: RelationshipRequest[]; received: RelationshipRequest[]; history: RelationshipRequest[] }>>('/grants/requests').then(response => response.data.data)
}

export function createRelationshipRequestApi(payload: Record<string, unknown>, idempotency_key = mutationKey()): Promise<RelationshipRequest> {
  return api.post<ApiResponse<RelationshipRequest>>('/grants/requests', { ...payload, idempotency_key }).then(response => response.data.data)
}

export function respondRelationshipApi(relationship_id: string, action: 'approve' | 'reject', authorization: { scope?: 'read' | 'write'; permissions?: string[]; tied_competition_ids?: string[]; replace_current_relationship_id?: string } = {}, idempotency_key = mutationKey()): Promise<RelationshipRequest> {
  return api.post<ApiResponse<RelationshipRequest>>('/grants/requests/respond', { relationship_id, action, ...authorization, idempotency_key }).then(response => response.data.data)
}

export function revokeRelationshipApi(relationship_id: string, idempotency_key = mutationKey()): Promise<RelationshipRequest> {
  return api.post<ApiResponse<RelationshipRequest>>('/grants/requests/revoke', { relationship_id, idempotency_key }).then(response => response.data.data)
}

export function cancelRelationshipApi(relationship_id: string, idempotency_key = mutationKey()): Promise<RelationshipRequest> {
  return api.post<ApiResponse<RelationshipRequest>>('/grants/requests/respond', { relationship_id, action: 'cancel', idempotency_key }).then(response => response.data.data)
}

export function listFavoritesApi(): Promise<{ favorites: Array<{ athlete_mapped_pk: string }> }> {
  return api.get<ApiResponse<{ favorites: Array<{ athlete_mapped_pk: string }> }>>('/grants/favorites').then(response => response.data.data)
}

export function setFavoriteApi(athlete_mapped_pk: string, action: 'add' | 'remove'): Promise<unknown> {
  return api.post<ApiResponse<unknown>>('/grants/favorites', { athlete_mapped_pk, action }).then(response => response.data.data)
}

export interface RelationshipNotification {
  notification_id: string
  kind: string
  payload: Record<string, unknown>
  read_at: string | null
  created_at: string
}

export function listNotificationsApi(): Promise<{ notifications: RelationshipNotification[]; total: number }> {
  return api.get<ApiResponse<{ notifications: RelationshipNotification[]; total: number }>>('/grants/notifications').then(response => response.data.data)
}

export function markNotificationsReadApi(notification_ids: string[]): Promise<{ marked: number }> {
  const batches = Array.from({ length: Math.ceil(notification_ids.length / 100) }, (_, index) => notification_ids.slice(index * 100, index * 100 + 100))
  return Promise.all(batches.map(batch => api.post<ApiResponse<{ marked: number }>>('/grants/notifications/read', { notification_ids: batch }))).then(responses => ({ marked: responses.reduce((total, response) => total + response.data.data.marked, 0) }))
}
