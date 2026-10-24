import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { Schedule } from "@/features/admin-scheduling/api"
import { formatBeijingTime } from "@/features/admin-scheduling/time"
import { apiRequest } from "@/lib/api/client"
import { localizedLabel } from "@/lib/labels"

export function LiveSchedulePanel({ instanceId, status }: { instanceId: string; status: string }) {
  const [open, setOpen] = useState("")
  const query = useQuery({
    queryKey: ["live-schedules", instanceId, status],
    queryFn: () => apiRequest<Schedule[]>(`/live-instances/${instanceId}/schedules`),
    enabled: !!open && status !== "terminated",
    staleTime: 0,
  })
  return (
    <Accordion type="single" collapsible value={open} onValueChange={setOpen}>
      <AccordionItem value="plans">
        <AccordionTrigger>实盘运行计划</AccordionTrigger>
        <AccordionContent className="flex min-w-0 flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            计划由本实盘自动管理；暂停时停用、恢复时重新安排，终止后清除。使用页面顶部的实盘启停按钮管理，无需系统管理员维护。
          </p>
          {status === "terminated" ? (
            <p>实盘已终止，专属计划已自动清除。</p>
          ) : (
            <>
              {query.isPending && <Skeleton className="h-20 w-full" />}
              {query.error && (
                <Alert variant="destructive">
                  <AlertDescription>
                    {query.error.message}
                    <Button variant="link" onClick={() => void query.refetch()}>
                      重试加载计划
                    </Button>
                  </AlertDescription>
                </Alert>
              )}
              {query.data && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>阶段</TableHead>
                      <TableHead>计划（北京时间）</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead>下次执行</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {query.data.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell>
                          {localizedLabel(String(row.configuration?.phase ?? ""))}
                        </TableCell>
                        <TableCell>{row.schedule_expression}</TableCell>
                        <TableCell>
                          <Badge variant="secondary">{row.enabled ? "启用" : "停用"}</Badge>
                        </TableCell>
                        <TableCell>
                          {row.enabled ? formatBeijingTime(row.next_run_at) : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </>
          )}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
