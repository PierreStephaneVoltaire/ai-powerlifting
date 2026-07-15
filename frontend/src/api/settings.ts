import axios from 'axios'
import { cachedGet, invalidateDomain, invalidateDomains } from './cache'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export interface ProfileTag {
  tag: string
  approved: boolean
  proposed_by: string
}

export type AppRole = 'athlete' | 'coach' | 'handler'

export interface TrainingMaxes {
  squat_kg: number
  bench_kg: number
  deadlift_kg: number
}

export interface UserSettings {
  pk: string
  mapped_pk?: string
  discord_id: string
  discord_username: string
  avatar_url: string | null
  nickname: string
  profile_visibility: 'private' | 'public'
  display_name: string
  bio: string
  public_training_summary_enabled: boolean
  ranking_country: string | null
  ranking_region: string | null
  age_class: 'open' | 'subjunior' | 'junior' | 'master1' | 'master2' | 'master3' | 'master4'
  tags: ProfileTag[]
  sex: 'male' | 'female' | null
  bodyweight_kg: number | null
  training_maxes: TrainingMaxes | null
  federations: string[]
  roles: AppRole[]
  active_role: AppRole
  athlete_basics_complete: boolean
  profile_complete: boolean
  created_at: string
  updated_at: string
}

export async function getSettings(): Promise<UserSettings> {
  const data = await cachedGet(api, '/settings', ['settings'])
  return data.data
}

export async function updateNickname(nickname: string): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/settings/nickname', { nickname })
  await invalidateDomains(['settings', 'profile:current'])
  return res.data.data
}

export async function updateProfile(input: {
  profile_visibility: 'private' | 'public'
  display_name: string
  bio: string
  public_training_summary_enabled?: boolean
}): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/settings/profile', input)
  await invalidateDomains(['settings', 'profile:current'])
  return res.data.data
}

export function isValidProfileAvatarType(file: File): boolean {
  return ['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)
}

export const MAX_PROFILE_AVATAR_SIZE = 8 * 1024 * 1024

export async function uploadProfileAvatar(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<UserSettings> {
  const formData = new FormData()
  formData.append('avatar', file)

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.withCredentials = true

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    })

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText)
          invalidateDomains(['settings', 'profile:current'])
          resolve(response.data)
        } catch {
          reject(new Error('Invalid response from server'))
        }
        return
      }

      try {
        const response = JSON.parse(xhr.responseText)
        reject(new Error(response.error || 'Profile picture upload failed'))
      } catch {
        reject(new Error('Profile picture upload failed'))
      }
    })

    xhr.addEventListener('error', () => {
      reject(new Error('Network error during profile picture upload'))
    })

    xhr.open('POST', `${API_BASE}/settings/avatar`)
    xhr.send(formData)
  })
}


export async function updateRankingLocation(input: {
  ranking_country: string | null
  ranking_region: string | null
}): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/settings/ranking-location', input)
  await invalidateDomains(['settings', 'stats:percentile'])
  return res.data.data
}

export async function updateAgeClass(input: {
  age_class: UserSettings['age_class'] | null
}): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/settings/age-class', input)
  await invalidateDomains(['settings', 'stats:percentile'])
  return res.data.data
}

// ─── Tags (FEAT-8) ──────────────────────────────────────────────────────────

export async function addTag(tag: string): Promise<UserSettings> {
  const res = await api.post<{ data: UserSettings }>('/settings/tags', { tag })
  await invalidateDomains(['settings', 'profile:current'])
  return res.data.data
}

export async function removeTag(tag: string): Promise<UserSettings> {
  const res = await api.delete<{ data: UserSettings }>(`/settings/tags/${encodeURIComponent(tag)}`)
  await invalidateDomains(['settings', 'profile:current'])
  return res.data.data
}

export async function approveTag(tag: string): Promise<UserSettings> {
  const res = await api.post<{ data: UserSettings }>(`/settings/tags/${encodeURIComponent(tag)}/approve`)
  await invalidateDomains(['settings', 'profile:current'])
  return res.data.data
}

export async function proposeTag(targetNickname: string, tag: string): Promise<unknown> {
  const res = await api.post<{ data: unknown }>('/settings/tags/propose', {
    target_nickname: targetNickname,
    tag,
  })
  await invalidateDomains(['profiles:search'])
  return res.data.data
}
