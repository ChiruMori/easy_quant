import { apiRequest } from "@/lib/api/client"

export interface Schedule {
  id: string
  task_type: string
  schedule_kind: string
  schedule_expression: string
  timezone: string
  enabled: boolean
  next_run_at: string
  configuration?: Record<string, unknown>
}
export const listSchedules = () => apiRequest<Schedule[]>("/admin/schedules")
export const createSchedule = (payload: Omit<Schedule, "id" | "next_run_at">) =>
  apiRequest<Schedule>("/admin/schedules", { method: "POST", body: JSON.stringify(payload) })
export const updateSchedule = (
  id: string,
  payload: Partial<
    Pick<
      Schedule,
      | "enabled"
      | "task_type"
      | "schedule_kind"
      | "schedule_expression"
      | "timezone"
      | "configuration"
    >
  >,
) =>
  apiRequest<Schedule>(`/admin/schedules/${id}`, { method: "PATCH", body: JSON.stringify(payload) })
export const runSchedule = (id: string, key: string) =>
  apiRequest<{ id: string; status: string }>(`/admin/schedules/${id}/run`, {
    method: "POST",
    headers: { "Idempotency-Key": key },
  })
export interface JobRecord {
  id: string
  job_type: string
  status: string
  available_at: string
  lease_until?: string | null
  lease_expired?: boolean
  attempt_count: number
  live_instance?: { id: string; name: string } | null
  result_summary?: Record<string, unknown>
  error_summary?: { message?: string }
}
export interface AuditRecord {
  id: string
  action: string
  resource_type: string
  resource_id: string
  occurred_at: string
  trigger_source: string
}
export interface JobPage {
  items: JobRecord[]
  total: number
  page: number
  page_size: number
}
export const listJobs = (page = 1) => apiRequest<JobPage>(`/admin/jobs?page=${page}&page_size=20`)
export const listAuditEvents = () => apiRequest<AuditRecord[]>("/admin/audit-events")

export const deleteSchedule = (id: string) =>
  apiRequest(`/admin/schedules/${id}`, {
    method: "DELETE",
    body: JSON.stringify({ confirmed: true }),
  })
