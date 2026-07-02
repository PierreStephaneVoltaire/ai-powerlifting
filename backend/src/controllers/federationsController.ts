import { invokeLambda } from '../utils/lambda'
import type {
  FederationDisplayOptions,
  FederationLibrary,
  FederationStandard,
  MasterFederation,
} from '@powerlifting/types'

// Federations live across two tables, all owned by the pl_federation layer
// (FederationStore) and exposed via Fission functions. The backend is a pure
// auth/pk router — NO DynamoDB.
//
//  - Master directory: POWERLIFTING_USER_FEDERATIONS_TABLE, pk="operator",
//    sk="FED#<masterId>". federation_master_list (scan + normalize) /
//    federation_master_update (admin edit).
//  - Per-user library: if-health, pk=<user>, sk="federations#v1", shape
//    {federations, qualification_standards}. federation_user_library_get /
//    federation_user_library_set.
//
// The AI-side per-user library (sk="federation_library#v1", shape {entries}) is
// a separate feature owned by FederationLibraryStore / the federation_library_*
// tools — not used by this controller.

export type FederationUpdate = {
  name?: string
  abbreviation?: string | null
  region?: string | null
  website_url?: string | null
  status?: 'active' | 'archived'
  has_standards?: boolean
  standard_unit?: 'kg' | 'dots' | null
  standards?: Record<string, FederationStandard>
  display_options?: FederationDisplayOptions | null
  parent_federation_abbr?: string | null
  membership_group?: string[]
}

export async function listFederations(): Promise<MasterFederation[]> {
  return (await invokeLambda('federation_master_list', {})) as MasterFederation[]
}

export async function updateFederation(masterId: string, updates: FederationUpdate): Promise<void> {
  await invokeLambda('federation_master_update', { master_id: masterId, updates })
}

export async function getFederationLibrary(pk: string): Promise<FederationLibrary> {
  return (await invokeLambda('federation_user_library_get', { pk })) as FederationLibrary
}

export async function updateFederationLibrary(
  pk: string,
  library: Pick<FederationLibrary, 'federations' | 'qualification_standards'>,
): Promise<FederationLibrary> {
  return (await invokeLambda('federation_user_library_set', {
    pk,
    federations: library.federations ?? [],
    qualification_standards: library.qualification_standards ?? [],
  })) as FederationLibrary
}
