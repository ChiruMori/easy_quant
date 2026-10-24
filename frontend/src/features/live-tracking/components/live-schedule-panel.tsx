import { useQuery } from "@tanstack/react-query"
import { CalendarClock, ChevronDown, ChevronUp, Pencil } from "lucide-react"
import { useState } from "react"

import { EmptyState } from "@/components/app-shell"
import { IconButton } from "@/components/icon-button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
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
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Schedule | null>(null)
  const [expression, setExpression] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const query = useQuery({
    queryKey: ["live-schedules", instanceId, status],
    queryFn: () => apiRequest<Schedule[]>(`/live-instances/${instanceId}/schedules`),
    enabled: open,
    staleTime: 0,
  })
  return (
    <>
      <Card className="min-w-0">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-2">
            <CardTitle className="flex items-center gap-2">
              <CalendarClock className="size-5 text-primary" />
              实盘运行计划
            </CardTitle>
            <CardDescription>
              {status === "terminated"
                ? "已停止触发，保留终止时的计划配置。"
                : "暂停实盘后可修改触发时间；恢复时自动按新计划运行。"}
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            aria-label="实盘运行计划"
            aria-expanded={open}
            aria-controls={`plans-${instanceId}`}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? "收起计划" : "查看计划"}
            {open ? <ChevronUp data-icon="inline-end" /> : <ChevronDown data-icon="inline-end" />}
          </Button>
        </CardHeader>
        {open && (
          <CardContent id={`plans-${instanceId}`} className="flex min-w-0 flex-col gap-3">
            {query.isPending && <Skeleton className="h-20 w-full" />}
            {query.error && (
              <Alert variant="destructive">
                <AlertDescription>
                  {query.error.message}
                  <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                    重试加载计划
                  </Button>
                </AlertDescription>
              </Alert>
            )}
            {query.data?.length === 0 && (
              <EmptyState title="暂无运行计划" message="此实盘没有可用的历史计划配置。" />
            )}
            {!!query.data?.length && (
              <Table aria-label="实盘计划列表">
                <TableHeader>
                  <TableRow>
                    <TableHead>阶段</TableHead>
                    <TableHead>时间表达式</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>下次执行（北京时间）</TableHead>
                    {status === "paused" && <TableHead>操作</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>
                        {localizedLabel(String(row.configuration?.phase ?? ""))}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{row.schedule_expression}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">
                          {status === "terminated" ? "已终止" : row.enabled ? "启用" : "停用"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {row.enabled && status === "active"
                          ? formatBeijingTime(row.next_run_at)
                          : "—"}
                      </TableCell>
                      {status === "paused" && (
                        <TableCell>
                          <IconButton
                            icon={Pencil}
                            label={`编辑${localizedLabel(String(row.configuration?.phase ?? ""))}时间`}
                            onClick={() => {
                              setEditing(row)
                              setExpression(row.schedule_expression)
                              setError("")
                            }}
                          />
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        )}
      </Card>
      <Dialog
        open={!!editing}
        onOpenChange={(value) => {
          if (!value && !busy) setEditing(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              修改{localizedLabel(String(editing?.configuration?.phase ?? ""))}触发时间
            </DialogTitle>
            <DialogDescription>
              仅修改本实盘的时间表达式，保存后仍保持暂停；恢复实盘后生效。
            </DialogDescription>
          </DialogHeader>
          <form
            className="flex flex-col gap-5"
            onSubmit={async (event) => {
              event.preventDefault()
              if (!editing || busy || status !== "paused") return
              setBusy(true)
              setError("")
              try {
                await apiRequest(`/live-instances/${instanceId}/schedules/${editing.id}`, {
                  method: "PATCH",
                  body: JSON.stringify({ schedule_expression: expression }),
                })
                await query.refetch()
                setEditing(null)
              } catch (caught) {
                setError(caught instanceof Error ? caught.message : "保存失败，请重试")
              } finally {
                setBusy(false)
              }
            }}
          >
            <Field>
              <FieldLabel htmlFor="live-plan-expression">Cron 表达式</FieldLabel>
              <Input
                id="live-plan-expression"
                value={expression}
                onChange={(event) => setExpression(event.target.value)}
                maxLength={120}
                required
                disabled={busy}
                className="font-mono"
              />
              <FieldDescription>
                五段格式：分 时 日 月 星期；例如 30 10 * *
                1-5。时区固定为北京时间，盘中阶段仍仅在交易时段运行，每阶段每交易日执行一次。
              </FieldDescription>
            </Field>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {status !== "paused" && (
              <Alert variant="destructive">
                <AlertDescription>实盘状态已变化，请暂停后再修改计划。</AlertDescription>
              </Alert>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => setEditing(null)}
              >
                取消
              </Button>
              <Button type="submit" disabled={busy || status !== "paused"}>
                {busy ? "正在保存…" : "保存时间"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
