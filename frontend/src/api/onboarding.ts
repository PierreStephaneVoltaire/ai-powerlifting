import axios from 'axios'
import type { AppRole, TrainingMaxes, UserSettings } from './settings'
import { invalidateDomain, invalidateDomains } from './cache'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export type OnboardingStep = 'role' | 'profile' | 'athlete_basics' | 'done' | null

export interface OnboardingStatus {
  is_onboarded: boolean
  next_step: OnboardingStep
  state: {
    roles: AppRole[]
    active_role: AppRole | null
    athlete_basics_complete: boolean
    profile_complete: boolean
  }
  has_athlete_basics: boolean
}

export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  const res = await api.get<{ data: OnboardingStatus }>('/onboarding/status')
  return res.data.data
}

export interface AthleteBasicsInput {
  sex: 'male' | 'female'
  country: string
  region: string | null
  bodyweight_kg: number
  training_maxes: TrainingMaxes
}

export async function submitAthleteBasics(input: AthleteBasicsInput): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/onboarding/athlete-basics', input)
  await invalidateDomains(['settings', 'profile:current', 'onboarding'])
  // Federation table reads can now resolve weight classes against the user's
  // bodyweight, so drop the cached federation list.
  await invalidateDomain('federations:master')
  return res.data.data
}

export interface OnboardingProfileInput {
  display_name: string
  bio: string
  profile_visibility: 'private' | 'public'
  public_training_summary_enabled: boolean
  federations: string[]
}

export async function submitOnboardingProfile(
  input: OnboardingProfileInput,
): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/onboarding/profile', input)
  await invalidateDomains(['settings', 'profile:current', 'onboarding'])
  return res.data.data
}

export interface UpdateRoleInput {
  roles: AppRole[]
  active_role: AppRole
}

export async function setRole(input: UpdateRoleInput): Promise<UserSettings> {
  const res = await api.put<{ data: UserSettings }>('/onboarding/role', input)
  await invalidateDomains(['settings', 'profile:current', 'onboarding'])
  return res.data.data
}
