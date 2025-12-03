import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authApi } from '../api/client'

interface AuthContextType {
  isAuthenticated: boolean
  username: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [username, setUsername] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkAuthStatus()
  }, [])

  const checkAuthStatus = async () => {
    const token = localStorage.getItem('auth_token')
    if (!token) {
      setLoading(false)
      return
    }

    try {
      const status = await authApi.checkStatus()
      setIsAuthenticated(status.authenticated)
      setUsername(status.username || null)
    } catch (error) {
      localStorage.removeItem('auth_token')
      setIsAuthenticated(false)
      setUsername(null)
    } finally {
      setLoading(false)
    }
  }

  const login = async (username: string, password: string) => {
    const response = await authApi.login(username, password)
    if (response.success && response.token) {
      localStorage.setItem('auth_token', response.token)
      setIsAuthenticated(true)
      setUsername(response.user)
    }
  }

  const logout = async () => {
    await authApi.logout()
    setIsAuthenticated(false)
    setUsername(null)
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, username, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

