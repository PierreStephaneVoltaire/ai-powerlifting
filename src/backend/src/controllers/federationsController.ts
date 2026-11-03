import { invokeLambda } from '../utils/lambda'
import type {
  FederationDisplayOptions,
  FederationLibrary,
  FederationStandard,
  MasterFederation,
} from '@powerlifting/types'

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
  return (await invokeLambda('pod_federation', { function: 'federation_master_list', })) as MasterFederation[]
}

export async function updateFederation(masterId: string, updates: FederationUpdate): Promise<void> {
  await invokeLambda('pod_federation', { function: 'federation_master_update',  master_id: masterId, updates })
}

export async function getFederationLibrary(pk: string): Promise<FederationLibrary> {
  return (await invokeLambda('pod_federation', { function: 'federation_user_library_get',  pk })) as FederationLibrary
}

export async function updateFederationLibrary(
  pk: string,
  library: Pick<FederationLibrary, 'federations' | 'qualification_standards'>,
): Promise<FederationLibrary> {
  return (await invokeLambda('pod_federation', { function: 'federation_user_library_set', 
    pk,
    federations: library.federations ?? [],
    qualification_standards: library.qualification_standards ?? [],
  })) as FederationLibrary
}
