import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { routePermission } from './routes'
import { checkSession, clearCache, clearDelegatedCachedRecords, readVerifiedIdentity, saveVerifiedIdentity } from '@/api/cache'
import { requestPartition, setRequestAthlete, setRequestPerson } from '@/api/context'
import { resumeMutations } from '@/api/drafts'
import { synchronizeOfflineQueue } from '@/api/offlineQueue'
import { shouldRestoreOwnContext } from './contextRestore'

export type IdentityProvider = 'discord' | 'authentik'
export type ActiveRole = 'athlete' | 'coach' | 'handler'
export interface AuthUser {
  provider: IdentityProvider
  sub: string
  username: string
  display_name: string
  avatar: string | null
  groups: string[]
  roles: string[]
  active_role: ActiveRole | null
  email: string | null
  discord_id: string
}
interface AuthState {
  user: AuthUser | null
  mapped_pk: string
  person_pk: string
  own_athlete_pk: string
  athlete_display_name: string
  permissions: string[]
  readOnly: boolean
  is_onboarded: boolean
  ranking_country: string | null
  ranking_region: string | null
  age_class: 'open' | 'subjunior' | 'junior' | 'master1' | 'master2' | 'master3' | 'master4'
  offline: boolean
}
interface AuthContextType extends AuthState {
  loading: boolean
  selectAthlete: (athlete: string) => Promise<void>
  selectRole: (role: ActiveRole) => void
  refreshAccess: () => Promise<void>
  signIn: () => void
  signInDiscord: () => void
  signInAuthentik: () => void
  signOut: () => Promise<void>
}
const empty: AuthState = { user: null, mapped_pk: 'operator', person_pk: '', own_athlete_pk: '', athlete_display_name: 'Demo', permissions: [], readOnly: true, is_onboarded: false, ranking_country: null, ranking_region: null, age_class: 'open', offline: false }
const signInDiscord = () => { window.location.href = '/api/auth/discord/login' }
const signInAuthentik = () => { window.location.href = '/api/auth/authentik/login' }
const AuthContext = createContext<AuthContextType>({ ...empty, loading: true, selectAthlete: async () => {}, selectRole: () => {}, refreshAccess: async () => {}, signIn: signInAuthentik, signInDiscord, signInAuthentik, signOut: async () => {} })
export function useAuth(domain?: string) {
  const value = useContext(AuthContext)
  const location = useLocation()
  const requiredDomain = domain || routePermission(location.pathname)?.replace(/:(read|write)$/, '') || 'program'
  return { ...value, readOnly: !value.permissions.includes(`${requiredDomain}:write`) }
}
const storageKey = (person: string) => `powerlifting-context:${person}`
function remembered(person: string): { athlete?: string; role?: ActiveRole } {
  try { return JSON.parse(localStorage.getItem(storageKey(person)) || '{}') } catch { return {} }
}
function remember(state: AuthState) {
  if (!state.person_pk) return
  localStorage.setItem(storageKey(state.person_pk), JSON.stringify({ athlete: state.mapped_pk, role: state.user?.active_role }))
}
async function getMe(athlete?: string) {
  const response = await fetch('/api/auth/me', { credentials: 'include', cache: 'no-store', headers: athlete ? { 'X-Selected-Athlete-Pk': athlete } : {} })
  if (!response.ok) throw new Error('Could not verify your access')
  return response.json()
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const location = useLocation()
  const [state, setState] = useState<AuthState>(empty)
  const stateRef = useRef(state)
  const [loading, setLoading] = useState(true)
  const sequence = useRef(0)
  const refreshing = useRef(false)
  const accept = useCallback(async (data: any, ticket: number, offline = false) => {
    if (ticket !== sequence.current) return
    const person = data.person_pk || ''
    const athlete = data.mapped_pk || 'operator'
    const permissions = data.access?.permissions || []
    const preference = remembered(person)
    const user = data.user ? { ...data.user, active_role: data.user.roles.includes(preference.role) ? preference.role : data.user.active_role } : null
    setRequestPerson(person)
    setRequestAthlete(athlete)
    await checkSession(person, permissions)
    if (ticket !== sequence.current) return
    const next: AuthState = {
      user, person_pk: person, mapped_pk: athlete, own_athlete_pk: data.own_athlete_pk || '',
      athlete_display_name: data.access?.athlete_display_name || (athlete === data.own_athlete_pk ? user?.display_name : null) || athlete,
      permissions, readOnly: !permissions.some((permission: string) => permission.endsWith(':write') && !permission.startsWith('settings:')),
      is_onboarded: data.onboarding?.is_onboarded === true,
      ranking_country: data.ranking_country || null, ranking_region: data.ranking_region || null, age_class: data.age_class || 'open',
      offline,
    }
    stateRef.current = next
    setState(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next)
    remember(next)
    if (!offline && person && data.user) await saveVerifiedIdentity(data, person, athlete)
  }, [])
  useEffect(() => {
    const ticket = ++sequence.current
    void (async () => {
      let offline = false
      let data: any
      try {
        data = await getMe()
      } catch (error) {
        if (navigator.onLine) throw error
        const cached = await readVerifiedIdentity<any>()
        if (!cached) throw error
        data = cached.data
        offline = true
      }
      const saved = !offline && data.person_pk && remembered(data.person_pk).athlete
      if (saved && saved !== data.mapped_pk) {
        const selected = await getMe(saved)
        if (selected.access?.permissions.includes('profile:read')) data = selected
        else await clearDelegatedCachedRecords(JSON.stringify([data.person_pk, saved]))
      }
      await accept(data, ticket, offline)
      if (!offline) {
        await resumeMutations(requestPartition())
        await synchronizeOfflineQueue()
      }
    })().catch(() => { setRequestPerson(''); setRequestAthlete('operator'); setState(empty) }).finally(() => setLoading(false))
  }, [accept])
  useEffect(() => {
    const current = stateRef.current
    if (!current.user || !shouldRestoreOwnContext(location.pathname, current.mapped_pk, current.own_athlete_pk)) return
    const ticket = ++sequence.current
    void (async () => {
      const data = await getMe()
      await accept(data, ticket)
      await resumeMutations(requestPartition())
      await synchronizeOfflineQueue()
    })().catch(() => {})
  }, [accept, location.pathname])
  const refreshAccess = useCallback(async () => {
    if (!navigator.onLine || refreshing.current) return
    refreshing.current = true
    const ticket = ++sequence.current
    try {
      const current = stateRef.current
      let data = await getMe(current.mapped_pk)
      if ((data.person_pk || '') !== current.person_pk) data = await getMe()
      await accept(data, ticket)
      await resumeMutations(requestPartition())
      await synchronizeOfflineQueue()
    } finally { refreshing.current = false }
  }, [accept])
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') void refreshAccess().catch(() => {}) }
    const denied = () => { void clearDelegatedCachedRecords(requestPartition()).finally(refresh) }
    const interval = window.setInterval(refresh, 30000)
    window.addEventListener('online', refresh)
    window.addEventListener('powerlifting-access-changed', denied)
    document.addEventListener('visibilitychange', refresh)
    return () => { clearInterval(interval); window.removeEventListener('online', refresh); window.removeEventListener('powerlifting-access-changed', denied); document.removeEventListener('visibilitychange', refresh) }
  }, [refreshAccess])
  const selectAthlete = async (athlete: string) => {
    if (!navigator.onLine) throw new Error('Connect to verify another Athlete’s access')
    const ticket = ++sequence.current
    const data = await getMe(athlete)
    if (!data.access?.permissions.includes('profile:read')) throw new Error('You no longer have access to this Athlete')
    await accept(data, ticket)
    await resumeMutations(requestPartition())
    await synchronizeOfflineQueue()
  }
  const selectRole = (role: ActiveRole) => {
    const current = stateRef.current
    if (!current.user?.roles.includes(role)) return
    const next = { ...current, user: { ...current.user, active_role: role } }
    stateRef.current = next
    setState(next)
    remember(next)
  }
  const signOut = async () => {
    const response = await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    if (!response.ok) throw new Error('Sign out was not confirmed')
    ++sequence.current
    await clearCache()
    setRequestPerson(''); setRequestAthlete('operator'); stateRef.current = empty; setState(empty)
  }
  return <AuthContext.Provider value={{ ...state, loading, selectAthlete, selectRole, refreshAccess, signIn: signInAuthentik, signInDiscord, signInAuthentik, signOut }}>{children}</AuthContext.Provider>
}
