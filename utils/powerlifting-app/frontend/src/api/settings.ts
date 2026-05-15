import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export interface UserSettings {
  discord_id: string
  discord_username: string
  avatar_url: string | null
  nickname: string
  profile_visibility: 'private' | 'public'
  display_name: string
  bio: string
  public_training_summary_enabled: boolean
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
  public_training_summary_enabled: boolean
}): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/settings/profile', input)
  return res.data.data
}
