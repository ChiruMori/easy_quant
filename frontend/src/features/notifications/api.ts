import { apiRequest } from "@/lib/api/client"

export interface Subscription {
  id: string
  channel: "email" | "ntfy"
  destination: string
  enabled: boolean
}
export const listSubscriptions = () => apiRequest<Subscription[]>("/notifications/subscriptions")
export const listDeliveries = () =>
  apiRequest<Array<{ id: string; status: string; channel: string }>>("/notifications/deliveries")
export const addSubscription = (channel: string, destination: string) =>
  apiRequest<Subscription>("/notifications/subscriptions", {
    method: "POST",
    body: JSON.stringify({ channel, destination }),
  })
export const updateSubscription = (id: string, enabled: boolean) =>
  apiRequest<Subscription>(`/notifications/subscriptions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  })
