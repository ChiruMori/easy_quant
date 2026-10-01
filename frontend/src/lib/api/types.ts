export interface ApiMeta {
  request_id?: string
  page?: number
  page_size?: number
  total?: number
}

export interface ApiSuccess<T> {
  data: T
  meta?: ApiMeta
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
  }
  meta?: ApiMeta
}

export interface CurrentUser {
  id: string
  username: string
  role: "admin" | "user"
  status: "active" | "disabled"
}

export interface CurrentSession {
  user: CurrentUser
  csrf_token?: string
}
