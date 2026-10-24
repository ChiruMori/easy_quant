import { useQuery } from "@tanstack/react-query"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { EmptyState } from "@/components/app-shell"
import { IconButton } from "@/components/icon-button"
import { PageNumberButtons } from "@/components/list-pagination"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { localizedLabel } from "@/lib/labels"

import { listJobs } from "../api"
import { formatBeijingTime } from "../time"

export function JobsPage() {
  const [requestedPage, setPage] = useState(1)
  const query = useQuery({
    queryKey: ["admin", "jobs", requestedPage],
    queryFn: () => listJobs(requestedPage),
    refetchInterval: 5000,
  })
  const page = query.data?.page ?? requestedPage
  const totalPages = Math.max(1, Math.ceil((query.data?.total ?? 0) / 20))
  if (query.isLoading) return <LoadingState label="正在加载后台任务" />
  if (query.error)
    return (
      <div className="flex flex-col gap-3">
        <ErrorState title="无法加载后台任务" message={query.error.message} />
        <Button onClick={() => void query.refetch()}>重试</Button>
      </div>
    )
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <h1 className="text-2xl font-semibold">后台任务</h1>
      {query.data?.items.length ? (
        <Table className="min-w-[720px]">
          <TableHeader>
            <TableRow>
              <TableHead>任务类型</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>计划时间（北京时间）</TableHead>
              <TableHead className="text-right">尝试次数</TableHead>
              <TableHead>执行结果</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.items.map((job) => (
              <TableRow key={job.id}>
                <TableCell>
                  {localizedLabel(job.job_type)}
                  {job.live_instance && (
                    <Link
                      className="block max-w-48 truncate font-medium text-primary hover:opacity-80"
                      title={`${job.live_instance.name} · ${job.live_instance.id}`}
                      to={`/live/${job.live_instance.id}`}
                    >
                      {job.live_instance.name || job.live_instance.id}
                    </Link>
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{localizedLabel(job.status)}</Badge>
                  {job.lease_expired && <Badge variant="destructive">租约已过期</Badge>}
                </TableCell>
                <TableCell>{formatBeijingTime(job.available_at)}</TableCell>
                <TableCell className="text-right tabular-nums">{job.attempt_count}</TableCell>
                <TableCell>
                  {job.error_summary?.message ||
                    (job.lease_expired ? "等待 worker 重新领取；请检查 worker 日志" : null) ||
                    (job.result_summary?.skipped ? String(job.result_summary.skipped) : null) ||
                    (job.job_type === "tdx-daily-update" && job.result_summary
                      ? `更新 ${Number(job.result_summary.imported_days ?? 0)} 日 / ${Number(job.result_summary.imported_rows ?? 0)} 条；未变化 ${Number(job.result_summary.unchanged_days ?? 0)} 日；休市 ${Number(job.result_summary.closed_days ?? 0)} 日`
                      : job.job_type === "index-daily-update" && job.result_summary
                        ? `同步 ${Number(job.result_summary.record_count ?? 0)} 条 · 截至 ${String(job.result_summary.end_day ?? "—")}`
                        : "—")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <EmptyState title="暂无后台任务" message="数据拉取、回测和通知任务会显示在这里。" />
      )}
      {query.data && query.data.total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            共 {query.data.total} 个任务 · 第 {page} / {totalPages} 页 · 按计划时间倒序
          </p>
          <nav aria-label="后台任务分页" className="flex flex-wrap items-center gap-2">
            <IconButton
              icon={ChevronLeft}
              label="上一页"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            />
            <PageNumberButtons page={page} totalPages={totalPages} onChange={setPage} />
            <IconButton
              icon={ChevronRight}
              label="下一页"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
            />
          </nav>
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              setPage(
                Math.max(
                  1,
                  Math.min(totalPages, Number(new FormData(event.currentTarget).get("page")) || 1),
                ),
              )
            }}
          >
            <Input
              name="page"
              aria-label="跳转页码"
              type="number"
              min={1}
              max={totalPages}
              className="w-20"
              required
            />
            <Button type="submit" variant="outline" size="sm">
              跳转
            </Button>
          </form>
        </div>
      )}
    </div>
  )
}
