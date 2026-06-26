import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

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
  created_at: string
  updated_at: string
}

export async function getSettings(): Promise<UserSettings> {
  const res = await api.get<{ data: UserSettings }>('/settings')
  return res.data.data
}

export async function updateNickname(nickname: string): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/settings/nickname', { nickname })
  return res.data.data
}

export async function updateProfile(input: {
  profile_visibility: 'private' | 'public'
  display_name: string
  bio: string
  public_training_summary_enabled?: boolean
}): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/settings/profile', input)
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
  return res.data.data
}

export async function updateAgeClass(input: {
  age_class: UserSettings['age_class'] | null
}): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/settings/age-class', input)
  return res.data.data
}
