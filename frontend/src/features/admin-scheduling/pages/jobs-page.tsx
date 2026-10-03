import { useQuery } from "@tanstack/react-query"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { EmptyState } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
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

export function JobsPage() {
  const query = useQuery({ queryKey: ["admin", "jobs"], queryFn: listJobs, refetchInterval: 5000 })
  if (query.isLoading) return <LoadingState label="正在加载后台任务" />
  if (query.error) return <ErrorState title="无法加载后台任务" message={query.error.message} />
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">后台任务</h1>
      {query.data?.length ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>任务类型</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>计划时间</TableHead>
              <TableHead className="text-right">尝试次数</TableHead>
              <TableHead>执行结果</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.map((job) => (
              <TableRow key={job.id}>
                <TableCell>{localizedLabel(job.job_type)}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{localizedLabel(job.status)}</Badge>
                  {job.lease_expired && <Badge variant="destructive">租约已过期</Badge>}
                </TableCell>
                <TableCell>{new Date(job.available_at).toLocaleString("zh-CN")}</TableCell>
                <TableCell className="text-right tabular-nums">{job.attempt_count}</TableCell>
                <TableCell>
                  {job.error_summary?.message ||
                    (job.lease_expired ? "等待 worker 重新领取；请检查 worker 日志" : null) ||
                    (job.job_type === "tdx-daily-update" && job.result_summary
                      ? `更新 ${Number(job.result_summary.imported_days ?? 0)} 日 / ${Number(job.result_summary.imported_rows ?? 0)} 条；未变化 ${Number(job.result_summary.unchanged_days ?? 0)} 日；休市 ${Number(job.result_summary.closed_days ?? 0)} 日`
                      : "—")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <EmptyState title="暂无后台任务" message="数据拉取、回测和通知任务会显示在这里。" />
      )}
    </div>
  )
}
