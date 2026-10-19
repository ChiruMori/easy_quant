import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { DatePicker } from "@/components/date-picker"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { localizedLabel } from "@/lib/labels"

import { getAcquisition, listIndices, syncIndices } from "../api"
import type { Acquisition } from "../types"

export function IndicesPanel() {
  const client = useQueryClient()
  const catalog = useQuery({ queryKey: ["admin", "indices"], queryFn: listIndices })
  const [selected, setSelected] = useState<string[]>([])
  const [lastTask, setLastTask] = useState<Acquisition | null>(null)
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const sending = useRef(false)
  const handled = useRef("")
  const taskQuery = useQuery({
    queryKey: ["admin", "indices", "task", lastTask?.id],
    queryFn: () => getAcquisition(lastTask!.id),
    enabled: Boolean(lastTask),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "queued") ? 1000 : false,
  })
  const task = taskQuery.data ?? lastTask
  const running = submitting || ["queued", "running"].includes(task?.status ?? "")
  useEffect(() => {
    if (!task || !["succeeded", "failed"].includes(task.status) || handled.current === task.id)
      return
    handled.current = task.id
    void client.invalidateQueries({ queryKey: ["admin", "indices"], exact: true })
    void client.invalidateQueries({ queryKey: ["admin", "market-data", "coverage"] })
  }, [task, client])
  if (catalog.isLoading) return <LoadingState label="正在加载指数数据" />
  if (catalog.error) return <ErrorState title="无法加载指数目录" message={catalog.error.message} />
  const items = catalog.data?.items ?? []
  const endDay = catalog.data?.recommended_end_day ?? ""
  const toggle = (symbol: string) =>
    setSelected((values) =>
      values.includes(symbol) ? values.filter((value) => value !== symbol) : [...values, symbol],
    )
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <p className="text-sm text-muted-foreground">
        主要指数 {items.length} 个 · 已有日线 {items.filter((item) => item.record_count > 0).length}{" "}
        个 · 建议同步至 {endDay || "—"}。仅用于研究和基准，不可交易。
      </p>
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>同步指数历史日线</CardTitle>
          <CardDescription>
            默认不勾选指数。先选择指数，再填写日期区间；无需先刷新股票信息。数据固定不复权，使用已启用的日线来源。日常更新可到系统管理的定时任务执行“主要指数日线同步”；通达信增量仅更新股票。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={running}
              onClick={() => setSelected(items.map((item) => item.symbol))}
            >
              全选主要指数
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={running}
              onClick={() => setSelected([])}
            >
              清空选择
            </Button>
            <span className="self-center text-sm text-muted-foreground">
              已选择 {selected.length} 个指数
            </span>
          </div>
          <div className="min-w-0 overflow-x-auto">
            <Table className="min-w-[720px]">
              <TableHeader>
                <TableRow>
                  <TableHead>选择</TableHead>
                  <TableHead>指数</TableHead>
                  <TableHead>同步状态</TableHead>
                  <TableHead>已有区间</TableHead>
                  <TableHead className="text-right">日线条数</TableHead>
                  <TableHead>数据详情</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.symbol}>
                    <TableCell>
                      <input
                        type="checkbox"
                        aria-label={`选择${item.name}`}
                        checked={selected.includes(item.symbol)}
                        disabled={running}
                        onChange={() => toggle(item.symbol)}
                      />
                    </TableCell>
                    <TableCell>
                      <p className="font-medium">{item.name}</p>
                      <p className="text-xs text-muted-foreground">{item.symbol}</p>
                    </TableCell>
                    <TableCell>
                      <Badge variant={item.sync_status === "已更新" ? "success" : "secondary"}>
                        {item.sync_status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {item.first_trading_day
                        ? `${item.first_trading_day} 至 ${item.last_trading_day}`
                        : "尚无行情"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {item.record_count.toLocaleString("zh-CN")}
                    </TableCell>
                    <TableCell>
                      {item.record_count > 0 ? (
                        <Link className="underline" to={`/admin/data/instruments/${item.symbol}`}>
                          查看{item.name} K 线
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">同步后可查看</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <form
            onSubmit={async (event) => {
              event.preventDefault()
              if (sending.current || running) return
              setError("")
              const data = new FormData(event.currentTarget)
              const start = String(data.get("start_day")),
                end = String(data.get("end_day"))
              if (!selected.length) {
                setError("请至少选择一个指数")
                return
              }
              if (start > end) {
                setError("开始日期不得晚于结束日期")
                return
              }
              sending.current = true
              setSubmitting(true)
              try {
                setLastTask(
                  await syncIndices({ symbols: selected, start_day: start, end_day: end }),
                )
              } catch (caught) {
                setError(caught instanceof Error ? caught.message : "无法创建指数同步任务")
              } finally {
                sending.current = false
                setSubmitting(false)
              }
            }}
          >
            <FieldGroup>
              <FieldGroup className="sm:grid sm:grid-cols-2">
                <Field>
                  <FieldLabel htmlFor="index-start">指数开始日期</FieldLabel>
                  <DatePicker
                    id="index-start"
                    name="start_day"

                    defaultValue={endDay ? `${Number(endDay.slice(0, 4)) - 10}-01-01` : ""}
                    required
                    disabled={running}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="index-end">指数结束日期</FieldLabel>
                  <DatePicker
                    id="index-end"
                    name="end_day"

                    defaultValue={endDay}
                    required
                    disabled={running}
                  />
                </Field>
              </FieldGroup>
              {catalog.data?.calendar_estimated && (
                <p className="text-sm text-muted-foreground">
                  交易日历尚未覆盖目标日期，建议截止日为估算；同步结果以真实来源为准。
                </p>
              )}
              {error && (
                <Alert variant="destructive">
                  <AlertTitle>无法同步指数</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <Button type="submit" disabled={running}>
                {running ? "指数同步处理中…" : "同步所选指数"}
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
      {task && (
        <Alert role="status" variant={task.status === "failed" ? "destructive" : "default"}>
          <AlertTitle>指数同步任务：{localizedLabel(task.status)}</AlertTitle>
          <AlertDescription>
            <p className="break-all">{task.id}</p>
            <p>
              {task.record_count ?? 0} 条{task.message ? ` · ${task.message}` : ""}
            </p>
            {task.failed_symbols?.map((item) => (
              <p key={item.symbol}>
                {item.symbol}：{item.message}
              </p>
            ))}
            {task.status === "failed" && (
              <p>请检查日线来源配置和失败明细，修正后可重新同步相同区间。</p>
            )}
          </AlertDescription>
        </Alert>
      )}
      {taskQuery.error && (
        <Alert variant="destructive">
          <AlertTitle>任务状态刷新失败</AlertTitle>
          <AlertDescription>{taskQuery.error.message}</AlertDescription>
        </Alert>
      )}
      {!!task?.attempts?.length && (
        <Card>
          <CardHeader>
            <CardTitle>来源尝试明细</CardTitle>
            <CardDescription>来源失败不会补造行情，重试覆盖相同业务日期。</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            {task.attempts.map((attempt, index) => (
              <p className="break-words" key={index}>
                {attempt.symbol && `${attempt.symbol} · `}
                {attempt.source_key} · {localizedLabel(attempt.status)}
                {attempt.message ? ` · ${attempt.message}` : ""}
              </p>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
