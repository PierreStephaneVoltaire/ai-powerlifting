import axios from 'axios'
import { cachedGet, invalidateDomain } from './cache'
import type { VideoLibraryItem } from '@powerlifting/types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export interface PublicProfile {
  nickname: string
  display_name: string
  avatar_url: string | null
  bio: string
  profile_visibility: 'private' | 'public'
  public_training_summary_enabled: boolean
  is_self: boolean
  tags: string[]
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
}

export async function searchProfiles(query: string): Promise<PublicProfile[]> {
  const data = await cachedGet(api, `/profiles/search?q=${encodeURIComponent(query)}`, ['profiles:search'])
  return data.data
}

export async function fetchProfile(nickname: string): Promise<PublicProfile> {
  const data = await cachedGet(api, `/profiles/${encodeURIComponent(nickname)}`, [`profile:${nickname}`])
  return data.data
}

export async function fetchCurrentProfile(): Promise<PublicProfile> {
  const data = await cachedGet(api, '/profiles/current', ['profile:current'])
  return data.data
}
