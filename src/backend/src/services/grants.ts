import { callOperation } from '../utils/operations'

export type GrantType = 'coach' | 'handler'
export type GrantScope = 'read' | 'write'

interface Grant {
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

export interface ListGrantsInput {
  athlete_mapped_pk?: string
  grantee_mapped_pk?: string
  include_inactive?: boolean
}

export interface CheckGrantInput {
  athlete_mapped_pk: string
  actor_mapped_pk: string
  grant_type?: GrantType
  scope?: GrantScope
  tied_competition_id?: string
}

interface CheckGrantResult {
  allowed: boolean
  reason: string
  grant?: Grant
}

export async function listGrants(input: ListGrantsInput): Promise<GrantListResult> {
  return (await callOperation('grant_list', {
    athlete_mapped_pk: input.athlete_mapped_pk ?? '',
    grantee_mapped_pk: input.grantee_mapped_pk ?? '',
    include_inactive: Boolean(input.include_inactive),
  })) as GrantListResult
}

export async function checkGrant(input: CheckGrantInput): Promise<CheckGrantResult> {
  return (await callOperation('grant_check', {
    athlete_mapped_pk: input.athlete_mapped_pk,
    actor_mapped_pk: input.actor_mapped_pk,
    grant_type: input.grant_type ?? '',
    scope: input.scope ?? '',
    tied_competition_id: input.tied_competition_id ?? '',
  })) as CheckGrantResult
}
