import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { localizedLabel } from "@/lib/labels"

import { createSchedule, listSchedules, updateSchedule } from "../api"

export function SchedulesPage() {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ["admin", "schedules"], queryFn: listSchedules })
  const [taskType, setTaskType] = useState("market-data-nightly")
  if (query.isLoading) return <LoadingState label="正在加载定时任务" />
  if (query.error) return <ErrorState title="无法加载定时任务" message={query.error.message} />
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">定时任务</h1>
        <p className="text-muted-foreground">配置数据拉取和实盘分析计划，并随时停用。</p>
      </div>
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>新增定时任务</CardTitle>
          <CardDescription>使用五段 Cron 表达式，时区默认为 Asia/Shanghai。</CardDescription>
        </CardHeader>
        <form
          onSubmit={async (event) => {
            event.preventDefault()
            const form = event.currentTarget
            const data = new FormData(form)
            await createSchedule({
              task_type: taskType,
              schedule_kind: "cron",
              schedule_expression: String(data.get("expression")),
              timezone: String(data.get("timezone")),
              enabled: true,
            })
            form.reset()
            await client.invalidateQueries({ queryKey: ["admin", "schedules"] })
          }}
        >
          <CardContent>
            <FieldGroup>
              <Field>
                <FieldLabel>任务类型</FieldLabel>
                <Select value={taskType} onValueChange={setTaskType}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="market-data-acquisition">数据拉取</SelectItem>
                      <SelectItem value="market-data-nightly">盘后全量数据同步</SelectItem>
                      <SelectItem value="tdx-daily-update">通达信 A 股盘后增量</SelectItem>
                      <SelectItem value="live-analysis">实盘分析</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
                {taskType === "market-data-nightly" && (
                  <FieldDescription>
                    刷新交易日历、证券、行业、估值、财务与日线。分批任务可在任务与数据获取页面查看、重试。
                  </FieldDescription>
                )}
                {taskType === "tdx-daily-update" && (
                  <FieldDescription>
                    需先完成通达信全量导入。盘后补齐缺日，保留不复权口径；请保持后台任务进程运行。
                  </FieldDescription>
                )}
              </Field>
              <Field>
                <FieldLabel htmlFor="expression">Cron 表达式</FieldLabel>
                <Input id="expression" name="expression" defaultValue="0 22 * * 1-5" required />
              </Field>
              <Field>
                <FieldLabel htmlFor="timezone">时区</FieldLabel>
                <Input id="timezone" name="timezone" defaultValue="Asia/Shanghai" required />
              </Field>
            </FieldGroup>
          </CardContent>
          <CardFooter>
            <Button type="submit">创建任务</Button>
          </CardFooter>
        </form>
      </Card>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>任务</TableHead>
            <TableHead>计划</TableHead>
            <TableHead>时区</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>启停</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {query.data?.map((item) => (
            <TableRow key={item.id}>
              <TableCell>{localizedLabel(item.task_type)}</TableCell>
              <TableCell>{item.schedule_expression}</TableCell>
              <TableCell>{item.timezone}</TableCell>
              <TableCell>
                <Badge variant="secondary">{item.enabled ? "启用" : "停用"}</Badge>
              </TableCell>
              <TableCell>
                <Switch
                  aria-label={`${item.task_type}启停`}
                  checked={item.enabled}
                  onCheckedChange={async (enabled) => {
                    await updateSchedule(item.id, { enabled })
                    await client.invalidateQueries({ queryKey: ["admin", "schedules"] })
                  }}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
