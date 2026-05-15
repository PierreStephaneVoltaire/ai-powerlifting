import axios from 'axios'

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
}

export async function searchProfiles(query: string): Promise<PublicProfile[]> {
  const res = await api.get<{ data: PublicProfile[] }>('/profiles/search', {
    params: { q: query },
  })
  return res.data.data
}

export async function fetchProfile(nickname: string): Promise<PublicProfile> {
  const res = await api.get<{ data: PublicProfile }>(`/profiles/${encodeURIComponent(nickname)}`)
  return res.data.data
}
