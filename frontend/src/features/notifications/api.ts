import { apiRequest } from "@/lib/api/client"

export interface Subscription {
  name?: string
  id: string
  channel: "email" | "ntfy" | "dingtalk" | "feishu" | "wecom"
  signing_secret?: string
  destination: string
  enabled: boolean
}
export const listSubscriptions = () => apiRequest<Subscription[]>("/notifications/subscriptions")
export interface NotificationPage<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
export interface Delivery {
  id: string
  status: string
  channel: string
  attempts?: number
  updated_at?: string
  created_at?: string
  error?: string
  error_code?: string
}
export const listSubscriptionsPage = (page: number) =>
  apiRequest<NotificationPage<Subscription>>(
    `/notifications/subscriptions?page=${page}&page_size=10`,
  )
export const listDeliveries = (page = 1) =>
  apiRequest<NotificationPage<Delivery>>(`/notifications/deliveries?page=${page}&page_size=10`)
export const getSubscription = (id: string) =>
  apiRequest<Subscription>(`/notifications/subscriptions/${id}`)
export const addSubscription = (
  channel: string,
  destination: string,
  name: string,
  signing_secret?: string,
) =>
  apiRequest<Subscription>("/notifications/subscriptions", {
    method: "POST",
    body: JSON.stringify({ channel, destination, name, signing_secret }),
  })
export const updateSubscription = (
  id: string,
  enabled: boolean,
  name?: string,
  destination?: string,
  signing_secret?: string,
) =>
  apiRequest<Subscription>(`/notifications/subscriptions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled, name, destination, signing_secret }),
  })

export const testSubscription = (id: string) =>
  apiRequest<{ status: string; message: string }>(`/notifications/subscriptions/${id}/test`, {
    method: "POST",
  })
