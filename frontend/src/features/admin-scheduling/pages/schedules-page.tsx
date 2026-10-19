import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Pencil, Plus, Save, X } from "lucide-react"
import { useState } from "react"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { IconButton } from "@/components/icon-button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import { Textarea } from "@/components/ui/textarea"
import { localizedLabel } from "@/lib/labels"

import { createSchedule, listSchedules, runSchedule, type Schedule, updateSchedule } from "../api"

export function SchedulesPage() {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ["admin", "schedules"], queryFn: listSchedules })
  const [taskType, setTaskType] = useState("market-data-nightly")
  const [editing, setEditing] = useState<Schedule | null>(null)
  const [message, setMessage] = useState("")
  const [pending, setPending] = useState(false)
  const [runKeys] = useState(() => new Map<string, string>())
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "schedules"] })
  if (query.isLoading) return <LoadingState label="正在加载定时任务" />
  if (query.error) return <ErrorState title="无法加载定时任务" message={query.error.message} />
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">定时任务</h1>
        <p className="text-muted-foreground">
          停用后可编辑计划，也可随时手动执行一次；不改变下次定时执行时间。
        </p>
      </div>
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>{editing ? "编辑定时任务" : "新增定时任务"}</CardTitle>
          <CardDescription>使用五段 Cron 表达式，时区默认为 Asia/Shanghai。</CardDescription>
        </CardHeader>
        <form
          className="flex min-w-0 flex-col gap-5"
          key={editing?.id ?? "new"}
          onSubmit={async (event) => {
            event.preventDefault()
            const form = event.currentTarget
            if (pending) return
            const data = new FormData(form)
            setPending(true)
            setMessage("")
            try {
              const payload = {
                task_type: taskType,
                schedule_kind: String(data.get("kind")),
                schedule_expression: String(data.get("expression")),
                timezone: String(data.get("timezone")),
                enabled: !editing,
                configuration: JSON.parse(String(data.get("configuration") || "{}")) as Record<
                  string,
                  unknown
                >,
              }
              if (editing) await updateSchedule(editing.id, payload)
              else await createSchedule(payload)
              form.reset()
              setEditing(null)
              setMessage("计划已保存")
              await refresh()
            } catch (error) {
              setMessage(error instanceof Error ? error.message : "无法保存计划")
            } finally {
              setPending(false)
            }
          }}
        >
          <CardContent>
            <FieldGroup>
              <Field>
                <FieldLabel>任务类型</FieldLabel>
                <Select value={taskType} onValueChange={setTaskType}>
                  <SelectTrigger className="w-full" aria-label="任务类型">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="market-data-acquisition">指定数据集同步</SelectItem>
                      <SelectItem value="market-data-nightly">盘后综合数据同步</SelectItem>
                      <SelectItem value="index-daily-update">主要指数日线同步</SelectItem>
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
                    仅更新 A
                    股股票，不包含指数。需先完成通达信全量导入。盘后补齐缺日，保留不复权口径；请保持后台任务进程运行。
                  </FieldDescription>
                )}
                {taskType === "market-data-acquisition" && (
                  <FieldDescription>
                    同步一个指定数据集与日期区间；daily-update
                    模式仅更新最近已发布日线。与盘后综合同步有部分重叠。
                  </FieldDescription>
                )}
                {taskType === "index-daily-update" && (
                  <FieldDescription>
                    补齐七个主要指数至最近已发布交易日，固定不复权，使用已启用日线来源。无历史时从十年前年初开始；可保持停用并每天立即执行。
                  </FieldDescription>
                )}
              </Field>
              <Field>
                <FieldLabel htmlFor="kind">计划方式</FieldLabel>
                <select
                  id="kind"
                  name="kind"
                  defaultValue={editing?.schedule_kind ?? "cron"}
                  className="rounded-md border p-2"
                >
                  <option value="cron">Cron</option>
                  <option value="interval">固定间隔（秒）</option>
                </select>
              </Field>
              <Field>
                <FieldLabel htmlFor="expression">Cron 表达式</FieldLabel>
                <Input
                  id="expression"
                  name="expression"
                  defaultValue={editing?.schedule_expression ?? "0 22 * * 1-5"}
                  required
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="timezone">时区</FieldLabel>
                <Input
                  id="timezone"
                  name="timezone"
                  defaultValue={editing?.timezone ?? "Asia/Shanghai"}
                  required
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="schedule-configuration">任务配置 JSON</FieldLabel>
                <Textarea
                  id="schedule-configuration"
                  name="configuration"
                  defaultValue={JSON.stringify(editing?.configuration ?? {}, null, 2)}
                />
                <FieldDescription>
                  指定数据集同步可配置
                  dataset_key、symbols、start_day、end_day；仅更新最近发布日线可用{" "}
                  {'{"mode": "daily-update"}'}。指数同步默认七个主要指数，可配置
                  symbols、start_day、end_day。
                </FieldDescription>
              </Field>
            </FieldGroup>
          </CardContent>
          <CardFooter>
            <IconButton
              type="submit"
              disabled={pending}
              icon={editing ? Save : Plus}
              label={editing ? "保存计划" : "创建任务"}
            />
            {editing && <IconButton icon={X} label="取消编辑" onClick={() => setEditing(null)} />}
          </CardFooter>
        </form>
      </Card>
      {message && (
        <Alert>
          <AlertTitle>操作结果</AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>任务</TableHead>
            <TableHead>计划</TableHead>
            <TableHead>时区</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>启停</TableHead>
            <TableHead>操作</TableHead>
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
                  disabled={pending}
                  onCheckedChange={async (enabled) => {
                    setPending(true)
                    try {
                      await updateSchedule(item.id, { enabled })
                      await refresh()
                    } catch (error) {
                      setMessage(error instanceof Error ? error.message : "操作失败")
                    } finally {
                      setPending(false)
                    }
                  }}
                />
              </TableCell>
              <TableCell>
                <div className="flex gap-2">
                  <IconButton
                    icon={Pencil}
                    label="编辑"
                    disabled={item.enabled || pending}
                    onClick={() => {
                      setEditing(item)
                      setTaskType(item.task_type)
                    }}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={pending}
                    onClick={async () => {
                      setPending(true)
                      const key = runKeys.get(item.id) ?? crypto.randomUUID()
                      runKeys.set(item.id, key)
                      try {
                        const job = await runSchedule(item.id, key)
                        runKeys.delete(item.id)
                        setMessage(`任务 ${job.id} 已进入队列，可在后台任务页面查看结果`)
                      } catch (error) {
                        setMessage(error instanceof Error ? error.message : "执行失败")
                      } finally {
                        setPending(false)
                      }
                    }}
                  >
                    立即执行
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
