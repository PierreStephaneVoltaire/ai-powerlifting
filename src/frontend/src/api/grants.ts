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

interface GrantListResult {
  active: Grant[]
  inactive: Grant[]
  total: number
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
