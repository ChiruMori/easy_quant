import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"

import { TooltipProvider } from "@/components/ui/tooltip"
import { apiRequest, setCsrfToken } from "@/lib/api/client"
import type { CurrentSession, CurrentUser } from "@/lib/api/types"

interface AuthenticationState {
  user: CurrentUser | null
  loading: boolean
  refresh: () => Promise<void>
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthenticationContext = createContext<AuthenticationState | null>(null)
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
})

function AuthenticationProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)
  const refresh = useCallback(async () => {
    const current = await apiRequest<CurrentSession>("/auth/me")
    setUser(current.user)
    setCsrfToken(current.csrf_token)
  }, [])
  useEffect(() => {
    void refresh()
      .catch(() => {
        setUser(null)
        setCsrfToken(undefined)
      })
      .finally(() => setLoading(false))
  }, [refresh])
  const login = useCallback(async (username: string, password: string) => {
    const current = await apiRequest<CurrentSession>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    })
    setUser(current.user)
    setCsrfToken(current.csrf_token)
  }, [])
  const logout = useCallback(async () => {
    await apiRequest<void>("/auth/logout", { method: "POST" })
    setUser(null)
    setCsrfToken(undefined)
    queryClient.clear()
  }, [])
  const value = useMemo(
    () => ({ user, loading, refresh, login, logout }),
    [user, loading, refresh, login, logout],
  )
  return <AuthenticationContext.Provider value={value}>{children}</AuthenticationContext.Provider>
}

export function useAuthentication() {
  const value = useContext(AuthenticationContext)
  if (!value) throw new Error("useAuthentication 必须在 AppProviders 内使用")
  return value
}

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <AuthenticationProvider>{children}</AuthenticationProvider>
      </TooltipProvider>
    </QueryClientProvider>
  )
}
