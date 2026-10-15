import { useState } from "react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
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

export interface RunTiming {
  total_seconds: number
  stages: Record<string, number>
  hooks: Record<
    string,
    { count: number; total_seconds: number; average_seconds: number; max_seconds: number }
  >
  daily_hooks: Array<{ trading_day: string; hook: string; seconds: number }>
}
export const executionStageLabel = (stage: string) =>
  ({
    validation: "校验数据覆盖",
    warmup: "准备预热历史",
    loading_data: "读取行情",
    context: "准备策略上下文",
    strategy: "运行策略",
    snapshot: "生成数据快照",
    saving: "保存结果",
    completed: "已完成",
    failed: "执行失败",
  })[stage] ?? stage

export function RunTimingPanel({ timing }: { timing?: RunTiming }) {
  const [day, setDay] = useState("")
  if (!timing) return null
  const days = timing.daily_hooks ?? []
  const selectedDay = day || days.at(-1)?.trading_day
  return (
    <Card>
      <CardHeader>
        <CardTitle>运行耗时</CardTitle>
        <CardDescription>
          总耗时 {timing.total_seconds.toFixed(3)} 秒 · 宿主观测时间，hook 包含子进程通信与执行。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="grid gap-2 sm:grid-cols-3">
          {Object.entries(timing.stages).map(([stage, seconds]) => (
            <div key={stage}>
              <dt>{executionStageLabel(stage)}</dt>
              <dd>{seconds.toFixed(3)} 秒</dd>
            </div>
          ))}
        </dl>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Hook</TableHead>
              <TableHead>次数</TableHead>
              <TableHead>平均耗时（秒）</TableHead>
              <TableHead>最大耗时（秒）</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Object.entries(timing.hooks).map(([hook, value]) => (
              <TableRow key={hook}>
                <TableCell>
                  {localizedLabel(hook)} · {hook}
                </TableCell>
                <TableCell>{value.count}</TableCell>
                <TableCell>{value.average_seconds.toFixed(6)}</TableCell>
                <TableCell>{value.max_seconds.toFixed(6)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {days.length > 0 && (
          <>
            <Field>
              <FieldLabel htmlFor="timing-day">查看交易日 Hook 耗时</FieldLabel>
              <Input
                id="timing-day"
                type="date"
                value={selectedDay ?? ""}
                onChange={(event) => setDay(event.target.value)}
              />
            </Field>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>交易日</TableHead>
                  <TableHead>Hook</TableHead>
                  <TableHead>耗时（秒）</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {days
                  .filter((item) => item.trading_day === selectedDay)
                  .map((item) => (
                    <TableRow key={item.hook}>
                      <TableCell>{item.trading_day}</TableCell>
                      <TableCell>{item.hook}</TableCell>
                      <TableCell>{item.seconds.toFixed(6)}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </>
        )}
      </CardContent>
    </Card>
  )
}
