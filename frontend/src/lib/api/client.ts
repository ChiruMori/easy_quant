import type { ApiErrorBody, ApiSuccess } from "@/lib/api/types"

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: Record<string, unknown>,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

let csrfToken: string | undefined
let pendingWrites = 0
const pendingListeners = new Set<() => void>()

export const getPendingWrites = () => pendingWrites
export function subscribePendingWrites(listener: () => void) {
  pendingListeners.add(listener)
  return () => {
    pendingListeners.delete(listener)
  }
}
function changePendingWrites(delta: number) {
  pendingWrites += delta
  pendingListeners.forEach((listener) => listener())
}

export function setCsrfToken(value?: string) {
  csrfToken = value
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const writing = !["GET", "HEAD", "OPTIONS"].includes((options.method ?? "GET").toUpperCase())
  if (writing) changePendingWrites(1)
  try {
    return await performRequest<T>(path, options)
  } finally {
    if (writing) changePendingWrites(-1)
  }
}

async function performRequest<T>(path: string, options: RequestInit): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase()
  const headers = new Headers(options.headers)
  headers.set("Accept", "application/json")
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }
  if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-CSRF-Token", csrfToken)
  }

  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
  })
  const text = await response.text()
  let body: ApiSuccess<T> | ApiErrorBody | undefined
  if (text) {
    try {
      body = JSON.parse(text) as ApiSuccess<T> | ApiErrorBody
    } catch {
      throw new ApiError(response.status, "invalid_response", "服务器返回了无法解析的响应")
    }
  }
  if (!response.ok) {
    const error = (body as ApiErrorBody | undefined)?.error ?? {
      code: "http_error",
      message: `请求失败（HTTP ${response.status}）`,
    }
    throw new ApiError(response.status, error.code, error.message, error.details)
  }
  return (body as ApiSuccess<T> | undefined)?.data as T
}
