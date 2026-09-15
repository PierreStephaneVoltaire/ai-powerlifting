import api from './http'
import type { LiftProfile, VideoLibraryItem } from '@powerlifting/types'



export interface PublicProfile {
  person_pk?: string
  athlete_pk: string
  nickname: string
  display_name: string
  avatar_url: string | null
  bio: string
  profile_visibility: 'private' | 'public'
  public_training_summary_enabled: boolean
  is_self: boolean
  tags: string[]
  federations?: string[]
  roles?: string[]
  federation?: string | null
  weight_class_kg?: number | null
  practicing_for?: string | null
  summary?: {
    squat_kg: number | null
    bench_kg: number | null
    deadlift_kg: number | null
    total_kg: number | null
    bodyweight_kg: number | null
    dots: number | null
  }
  lift_videos?: VideoLibraryItem[]
  lift_profiles?: LiftProfile[]
}

export async function searchProfiles(query: string): Promise<PublicProfile[]> {
  return (await searchProfilePage({ query })).profiles
}

export interface ProfileSearchInput { query?: string; tags?: string[]; federations?: string[]; tag_mode?: 'and' | 'or'; role?: 'athlete' | 'coach'; cursor?: string }
export async function searchProfilePage(input: ProfileSearchInput): Promise<{ profiles: PublicProfile[]; next_cursor: string | null }> {
  const params = new URLSearchParams({ q: input.query || '', tag_mode: input.tag_mode || 'and' })
  for (const tag of input.tags || []) params.append('tag', tag)
  for (const federation of input.federations || []) params.append('federation', federation)
  if (input.role) params.set('role', input.role)
  if (input.cursor) params.set('cursor', input.cursor)
  const response = await api.get(`/profiles/search?${params}`)
  return response.data.data
}

export async function fetchProfile(nickname: string): Promise<PublicProfile> {
  const response = await api.get(`/profiles/${encodeURIComponent(nickname)}`)
  return response.data.data
}

export async function fetchCurrentProfile(): Promise<PublicProfile> {
  const response = await api.get('/profiles/current')
  return response.data.data
}
