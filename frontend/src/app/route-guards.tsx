import type { PropsWithChildren } from "react"
import { Navigate, useLocation } from "react-router-dom"

import { Forbidden, LoadingState } from "@/components/app-shell"

import { useAuthentication } from "./providers"

export function AuthenticatedGuard({ children }: PropsWithChildren) {
  const { user, loading } = useAuthentication()
  const location = useLocation()
  if (loading) return <LoadingState label="正在确认登录状态" />
  return user ? children : <Navigate to="/login" replace state={{ from: location.pathname }} />
}

export function AdminGuard({ children }: PropsWithChildren) {
  const { user } = useAuthentication()
  return user?.role === "admin" ? children : <Forbidden />
}
