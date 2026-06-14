import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

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

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        setUser(data.user)
        setMappedPk(data.mapped_pk || 'operator')
        setReadOnly(data.readOnly !== false)
        setRankingCountry(data.ranking_country || null)
        setRankingRegion(data.ranking_region || null)
      })
      .catch(() => {
        setUser(null)
        setMappedPk('operator')
        setReadOnly(true)
        setRankingCountry(null)
        setRankingRegion(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const signIn = () => {
    window.location.href = '/api/auth/discord/login'
  }

  const signOut = async () => {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    setUser(null)
    setMappedPk('operator')
    setReadOnly(true)
    setRankingCountry(null)
    setRankingRegion(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, mapped_pk, readOnly, ranking_country, ranking_region, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}
