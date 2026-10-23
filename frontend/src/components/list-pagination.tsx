import { Button } from "@/components/ui/button"

export function PageNumberButtons({
  page,
  totalPages,
  busy,
  onChange,
}: {
  page: number
  totalPages: number
  busy?: boolean
  onChange: (page: number) => void
}) {
  const pages = [...new Set([1, page - 1, page, page + 1, totalPages])]
    .filter((value) => value >= 1 && value <= totalPages)
    .sort((a, b) => a - b)
  return (
    <>
      {pages.map((value, index) => (
        <span key={value} className="flex items-center gap-2">
          {index > 0 && value - pages[index - 1] > 1 && <span aria-hidden="true">…</span>}
          <Button
            size="icon"
            variant={value === page ? "default" : "outline"}
            aria-label={`第 ${value} 页`}
            aria-current={value === page ? "page" : undefined}
            disabled={busy}
            onClick={() => onChange(value)}
          >
            {value}
          </Button>
        </span>
      ))}
    </>
  )
}

export function ListPagination({
  page,
  total,
  pageSize,
  busy,
  onChange,
  label,
  numbered = false,
}: {
  page: number
  total: number
  pageSize: number
  busy?: boolean
  onChange: (page: number) => void
  label: string
  numbered?: boolean
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
      {numbered && (
        <PageNumberButtons
          page={page}
          totalPages={Math.max(1, Math.ceil(total / pageSize))}
          busy={busy}
          onChange={onChange}
        />
      )}
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
