import { invokeLambda } from '../utils/lambda'

export type GrantType = 'coach' | 'handler'
export type GrantScope = 'read' | 'write'

export interface GrantTiedCompetitionDateMap {
  [competitionId: string]: string
}

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

export interface CreateGrantInput {
  athlete_mapped_pk: string
  grantee_mapped_pk: string
  grantee_nickname?: string
  grantee_discord_id?: string
  grantee_authentik_sub?: string
  grant_type: GrantType
  scope?: GrantScope
  tied_competition_ids?: string[]
  tied_competition_dates?: GrantTiedCompetitionDateMap
  note?: string
  created_by?: string
}

export interface RevokeGrantInput {
  athlete_mapped_pk: string
  sk: string
  revoked_by?: string
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

export interface CheckGrantResult {
  allowed: boolean
  reason: string
  grant?: Grant
}

export async function createGrant(input: CreateGrantInput): Promise<Grant> {
  const result = (await invokeLambda('pod_user', {
    function: 'grant_create',
    athlete_mapped_pk: input.athlete_mapped_pk,
    grantee_mapped_pk: input.grantee_mapped_pk,
    grantee_nickname: input.grantee_nickname ?? '',
    grantee_discord_id: input.grantee_discord_id ?? '',
    grantee_authentik_sub: input.grantee_authentik_sub ?? '',
    grant_type: input.grant_type,
    scope: input.scope ?? 'read',
    tied_competition_ids: input.tied_competition_ids ?? [],
    tied_competition_dates: input.tied_competition_dates ?? {},
    note: input.note ?? '',
    created_by: input.created_by ?? input.athlete_mapped_pk,
  })) as Grant | { error: string; message: string; existing?: Grant }
  if (result && typeof result === 'object' && 'error' in result) {
    return result as unknown as Grant
  }
  return result as Grant
}

export async function revokeGrant(input: RevokeGrantInput): Promise<Grant | { error: string }> {
  return (await invokeLambda('pod_user', {
    function: 'grant_revoke',
    athlete_mapped_pk: input.athlete_mapped_pk,
    sk: input.sk,
    revoked_by: input.revoked_by ?? input.athlete_mapped_pk,
  })) as Grant | { error: string }
}

export async function listGrants(input: ListGrantsInput): Promise<GrantListResult> {
  return (await invokeLambda('pod_user', {
    function: 'grant_list',
    athlete_mapped_pk: input.athlete_mapped_pk ?? '',
    grantee_mapped_pk: input.grantee_mapped_pk ?? '',
    include_inactive: Boolean(input.include_inactive),
  })) as GrantListResult
}

export async function checkGrant(input: CheckGrantInput): Promise<CheckGrantResult> {
  return (await invokeLambda('pod_user', {
    function: 'grant_check',
    athlete_mapped_pk: input.athlete_mapped_pk,
    actor_mapped_pk: input.actor_mapped_pk,
    grant_type: input.grant_type ?? '',
    scope: input.scope ?? '',
    tied_competition_id: input.tied_competition_id ?? '',
  })) as CheckGrantResult
}
