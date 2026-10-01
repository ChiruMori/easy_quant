import { useQuery } from "@tanstack/react-query"

import { EmptyState, ErrorState, LoadingState } from "@/components/app-shell"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { localizedLabel } from "@/lib/labels"

import { listAuditEvents } from "../api"

export function AuditPage() {
  const query = useQuery({ queryKey: ["admin", "audit"], queryFn: listAuditEvents })
  if (query.isLoading) return <LoadingState label="正在加载审计记录" />
  if (query.error) return <ErrorState title="无法加载审计记录" message={query.error.message} />
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">审计记录</h1>
      {query.data?.length ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>时间</TableHead>
              <TableHead>操作</TableHead>
              <TableHead>资源</TableHead>
              <TableHead>资源标识</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.map((event) => (
              <TableRow key={event.id}>
                <TableCell>{new Date(event.occurred_at).toLocaleString("zh-CN")}</TableCell>
                <TableCell>{localizedLabel(event.action)}</TableCell>
                <TableCell>{localizedLabel(event.resource_type)}</TableCell>
                <TableCell className="max-w-64 truncate" title={event.resource_id}>
                  {event.resource_id}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <EmptyState title="暂无审计记录" message="关键配置和状态变更会显示在这里。" />
      )}
    </div>
  )
}
