export type GrantType = 'coach' | 'handler'
export type GrantScope = 'read' | 'write'

export interface Grant {
  pk: string
  sk: string
  athlete_mapped_pk: string
  athlete_nickname: string
  grantee_mapped_pk: string
  grantee_nickname: string
  grantee_discord_id: string
  grantee_authentik_sub: string
  grant_type: GrantType
  scope: GrantScope
  tied_competition_ids: string[]
  expires_at: string
  revoked_at: string | null
  revoked_by: string | null
  created_by: string
  note: string
  last_edited_by: string
  created_at: string
  updated_at: string
}

export interface GrantListResult {
  active: Grant[]
  inactive: Grant[]
  total: number
}

export interface CreateGrantPayload {
  athlete_mapped_pk?: string
  grantee_mapped_pk: string
  grantee_nickname?: string
  grantee_discord_id?: string
  grantee_authentik_sub?: string
  grant_type: GrantType
  scope?: GrantScope
  tied_competition_ids?: string[]
  tied_competition_dates?: Record<string, string>
  note?: string
}

export interface CheckGrantResult {
  allowed: boolean
  reason: string
  grant?: Grant
}

async function jsonOk<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let body: unknown = null
    try {
      body = await res.json()
    } catch {}
    let message: string | undefined
    if (body && typeof body === 'object' && 'message' in body) {
      const m = (body as Record<string, unknown>).message
      if (typeof m === 'string') message = m
    }
    throw new Error(message || res.statusText || 'Request failed')
  }
  const body = (await res.json()) as { data: T }
  return body.data
}

export async function listGrantsApi(params: { athlete_mapped_pk?: string; grantee_mapped_pk?: string; include_inactive?: boolean } = {}): Promise<GrantListResult> {
  const search = new URLSearchParams()
  if (params.athlete_mapped_pk) search.set('athlete_mapped_pk', params.athlete_mapped_pk)
  if (params.grantee_mapped_pk) search.set('grantee_mapped_pk', params.grantee_mapped_pk)
  if (params.include_inactive) search.set('include_inactive', 'true')
  const qs = search.toString()
  const res = await fetch(`/api/grants/${qs ? `?${qs}` : ''}`, {
    credentials: 'include',
  })
  return jsonOk<GrantListResult>(res)
}

export async function createGrantApi(payload: CreateGrantPayload): Promise<Grant> {
  const res = await fetch('/api/grants', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return jsonOk<Grant>(res)
}

export async function revokeGrantApi(payload: { athlete_mapped_pk: string; sk: string }): Promise<Grant | { error: string }> {
  const res = await fetch('/api/grants', {
    method: 'DELETE',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return jsonOk<Grant | { error: string }>(res)
}

export async function checkGrantApi(params: {
  athlete_mapped_pk: string
  actor_mapped_pk?: string
  grant_type?: GrantType
  scope?: GrantScope
  tied_competition_id?: string
}): Promise<CheckGrantResult> {
  const search = new URLSearchParams()
  search.set('athlete_mapped_pk', params.athlete_mapped_pk)
  if (params.actor_mapped_pk) search.set('actor_mapped_pk', params.actor_mapped_pk)
  if (params.grant_type) search.set('grant_type', params.grant_type)
  if (params.scope) search.set('scope', params.scope)
  if (params.tied_competition_id) search.set('tied_competition_id', params.tied_competition_id)
  const res = await fetch(`/api/grants/check?${search.toString()}`, {
    credentials: 'include',
  })
  return jsonOk<CheckGrantResult>(res)
}
