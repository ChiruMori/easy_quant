import { Button } from "@/components/ui/button"

export function ListPagination({
  page,
  total,
  pageSize,
  busy,
  onChange,
  label,
}: {
  page: number
  total: number
  pageSize: number
  busy?: boolean
  onChange: (page: number) => void
  label: string
}) {
  return (
    <nav
      aria-label={label}
      className="flex flex-wrap items-center justify-between gap-3 sm:justify-end"
    >
      <Button variant="outline" disabled={busy || page <= 1} onClick={() => onChange(page - 1)}>
        上一页
      </Button>
      <p className="order-first w-full text-center text-sm text-muted-foreground sm:order-none sm:w-auto">
        第 {page} / {Math.max(1, Math.ceil(total / pageSize))} 页 · 共 {total} 条
      </p>
      <Button
        variant="outline"
        disabled={busy || page * pageSize >= total}
        onClick={() => onChange(page + 1)}
      >
        下一页
      </Button>
    </nav>
  )
}
