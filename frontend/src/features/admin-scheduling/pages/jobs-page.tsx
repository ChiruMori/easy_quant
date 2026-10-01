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
  const query = useQuery({ queryKey: ["admin", "jobs"], queryFn: listJobs })
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
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.map((job) => (
              <TableRow key={job.id}>
                <TableCell>{localizedLabel(job.job_type)}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{localizedLabel(job.status)}</Badge>
                </TableCell>
                <TableCell>{new Date(job.available_at).toLocaleString("zh-CN")}</TableCell>
                <TableCell className="text-right tabular-nums">{job.attempt_count}</TableCell>
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
