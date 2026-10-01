import { apiRequest } from "@/lib/api/client"

export interface ManagedUser {
  id: string
  username: string
  role: string
  status: string
}
export interface InvitationSummary {
  id: string
  expires_at: string
  used_at?: string
  revoked_at?: string
}
export const listUsers = () => apiRequest<ManagedUser[]>("/admin/users")
export const listInvitations = () => apiRequest<InvitationSummary[]>("/admin/invitations")
export const createInvitation = (lifetimeHours = 168) =>
  apiRequest<{ id: string; token: string }>("/admin/invitations", {
    method: "POST",
    body: JSON.stringify({ lifetime_hours: lifetimeHours }),
  })
export const updateUser = (id: string, values: { role?: string; status?: string }) =>
  apiRequest<ManagedUser>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(values) })
