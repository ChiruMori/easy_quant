import { apiRequest } from "@/lib/api/client"

export interface Schedule {
  id: string
  task_type: string
  schedule_kind: string
  schedule_expression: string
  timezone: string
  enabled: boolean
  next_run_at: string
}
export const listSchedules = () => apiRequest<Schedule[]>("/admin/schedules")
export const createSchedule = (payload: Omit<Schedule, "id" | "next_run_at">) =>
  apiRequest<Schedule>("/admin/schedules", { method: "POST", body: JSON.stringify(payload) })
export const updateSchedule = (
  id: string,
  payload: Partial<Pick<Schedule, "enabled" | "schedule_expression" | "timezone">>,
) =>
  apiRequest<Schedule>(`/admin/schedules/${id}`, { method: "PATCH", body: JSON.stringify(payload) })
export interface JobRecord {
  id: string
  job_type: string
  status: string
  available_at: string
  lease_until?: string | null
  lease_expired?: boolean
  attempt_count: number
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
export const listJobs = () => apiRequest<JobRecord[]>("/admin/jobs")
export const listAuditEvents = () => apiRequest<AuditRecord[]>("/admin/audit-events")
