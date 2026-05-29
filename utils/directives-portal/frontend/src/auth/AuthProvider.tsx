import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

interface AuthUser {
  discord_id: string
  username: string
  avatar: string | null
}

interface AuthContextType {
  user: AuthUser | null
  loading: boolean
  signIn: () => void
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  signIn: () => {},
  signOut: async () => {},
})

export function useAuth() {
  return useContext(AuthContext)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        setUser(data.user ?? null)
      })
      .catch(() => {
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const signIn = () => {
    window.location.href = '/api/auth/discord/login'
  }

  const signOut = async () => {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}