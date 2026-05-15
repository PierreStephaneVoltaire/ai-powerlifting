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
  signIn: () => void
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  mapped_pk: 'operator',
  readOnly: true,
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

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        setUser(data.user)
        setMappedPk(data.mapped_pk || 'operator')
        setReadOnly(data.readOnly !== false)
      })
      .catch(() => {
        setUser(null)
        setMappedPk('operator')
        setReadOnly(true)
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
  }

  return (
    <AuthContext.Provider value={{ user, loading, mapped_pk, readOnly, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}
