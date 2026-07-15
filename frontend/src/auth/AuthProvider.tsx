import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { checkSession, clearCache } from '@/api/cache'

export type IdentityProvider = 'discord' | 'authentik'

export interface AuthUser {
  provider: IdentityProvider
  sub: string
  username: string
  display_name: string
  avatar: string | null
  groups: string[]
  roles: string[]
  email: string | null
  discord_id: string
}

export interface EnabledProviders {
  discord: { enabled: boolean }
  authentik: { enabled: boolean }
}

interface AuthContextType {
  user: AuthUser | null
  loading: boolean
  mapped_pk: string
  readOnly: boolean
  ranking_country: string | null
  ranking_region: string | null
  age_class: 'open' | 'subjunior' | 'junior' | 'master1' | 'master2' | 'master3' | 'master4'
  providers: EnabledProviders
  /**
   * @deprecated Discord-specific sign-in. Kept as an alias for `signInDiscord`
   * to avoid breaking existing call sites; new code should call `signInDiscord`
   * (the original Discord path) or `signInAuthentik` (the new OIDC path) directly.
   */
  signIn: () => void
  signInDiscord: () => void
  signInAuthentik: () => void
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  mapped_pk: 'operator',
  readOnly: true,
  ranking_country: null,
  ranking_region: null,
  age_class: 'open',
  providers: { discord: { enabled: true }, authentik: { enabled: false } },
  signIn: () => {},
  signInDiscord: () => {},
  signInAuthentik: () => {},
  signOut: async () => {},
})

export function useAuth() {
  return useContext(AuthContext)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [mapped_pk, setMappedPk] = useState('operator')
  const [readOnly, setReadOnly] = useState(true)
  const [ranking_country, setRankingCountry] = useState<string | null>(null)
  const [ranking_region, setRankingRegion] = useState<string | null>(null)
  const [age_class, setAgeClass] = useState<AuthContextType['age_class']>('open')
  const [providers, setProviders] = useState<EnabledProviders>({
    discord: { enabled: true },
    authentik: { enabled: false },
  })

  useEffect(() => {
    fetch('/api/auth/providers', { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        if (data && typeof data === 'object') {
          setProviders({
            discord: { enabled: Boolean(data.discord?.enabled) },
            authentik: { enabled: Boolean(data.authentik?.enabled) },
          })
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        setUser(data.user)
        const pk = data.mapped_pk || 'operator'
        setMappedPk(pk)
        setReadOnly(data.readOnly !== false)
        setRankingCountry(data.ranking_country || null)
        setRankingRegion(data.ranking_region || null)
        setAgeClass(data.age_class || 'open')
        checkSession(pk).catch(() => {})
      })
      .catch(() => {
        setUser(null)
        setMappedPk('operator')
        setReadOnly(true)
        setRankingCountry(null)
        setRankingRegion(null)
        setAgeClass('open')
      })
      .finally(() => setLoading(false))
  }, [])

  const signInDiscord = () => {
    window.location.href = '/api/auth/discord/login'
  }

  const signInAuthentik = () => {
    window.location.href = '/api/auth/authentik/login'
  }

  const signOut = async () => {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    await clearCache().catch(() => {})
    setUser(null)
    setMappedPk('operator')
    setReadOnly(true)
    setRankingCountry(null)
    setRankingRegion(null)
    setAgeClass('open')
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        mapped_pk,
        readOnly,
        ranking_country,
        ranking_region,
        age_class,
        providers,
        signIn: signInDiscord,
        signInDiscord,
        signInAuthentik,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

