import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

interface AuthUser {
  discord_id: string
  username: string
  avatar: string | null
}

interface AuthContextType {
  user: AuthUser | null
  loading: boolean
  isOperator: boolean
  mappedPk: string | null
  signIn: () => void
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  isOperator: false,
  mappedPk: null,
  signIn: () => {},
  signOut: async () => {},
})

export function useAuth() {
  return useContext(AuthContext)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [isOperator, setIsOperator] = useState(false)
  const [mappedPk, setMappedPk] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        setUser(data.user ?? null)
        setIsOperator(data.is_operator ?? false)
        setMappedPk(data.mapped_pk ?? null)
      })
      .catch(() => {
        setUser(null)
        setIsOperator(false)
        setMappedPk(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const signIn = () => {
    window.location.href = '/api/auth/discord/login'
  }

  const signOut = async () => {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    setUser(null)
    setIsOperator(false)
    setMappedPk(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, isOperator, mappedPk, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}