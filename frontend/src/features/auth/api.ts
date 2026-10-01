import { apiRequest } from "@/lib/api/client"
import type { CurrentUser } from "@/lib/api/types"

export const acceptInvitation = (token: string, username: string, password: string) =>
  apiRequest<CurrentUser>("/auth/accept-invitation", {
    method: "POST",
    body: JSON.stringify({ token, username, password }),
  })
