import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { checkSession, clearCache } from '@/api/cache'

interface AuthUser {
  discord_id: string
  username: string
  avatar: string | null
}

interface AuthContextType {
  user: AuthUser | null
  loading: boolean
  mapped_pk: string
  readOnly: boolean
  ranking_country: string | null
  ranking_region: string | null
  age_class: 'open' | 'subjunior' | 'junior' | 'master1' | 'master2' | 'master3' | 'master4'
  signIn: () => void
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
  signIn: () => {},
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
        // Validate IndexedDB cache — wipes if user changed
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

  const signIn = () => {
    window.location.href = '/api/auth/discord/login'
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
    <AuthContext.Provider value={{ user, loading, mapped_pk, readOnly, ranking_country, ranking_region, age_class, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}
