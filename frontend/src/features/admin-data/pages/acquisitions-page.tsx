import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { localizedLabel } from "@/lib/labels"

import { startAcquisition } from "../api"
import type { Acquisition } from "../types"

export function AcquisitionsPage() {
  const [message, setMessage] = useState("尚未运行")
  const [running, setRunning] = useState(false)
  const [singleSymbol, setSingleSymbol] = useState("")
  const [syncDataset, setSyncDataset] = useState("daily-bars")
  const [lastTask, setLastTask] = useState<Acquisition | null>(null)

  async function run(task: Promise<{ id: string; status: string; record_count?: number }>) {
    setRunning(true)
    try {
      const result = await task
      setLastTask(result as Acquisition)
      setMessage(`${result.id} · ${localizedLabel(result.status)} · ${result.record_count ?? 0} 条`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "任务执行失败")
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-5">
      <Card>
        <CardHeader>
          <CardTitle>刷新基础数据</CardTitle>
          <CardDescription>
            证券基础信息由管理员手动刷新；交易日历用于判断数据时效。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button disabled={running} onClick={() => run(startAcquisition("securities", true))}>
            刷新全部股票信息
          </Button>
          <Button
            disabled={running}
            variant="outline"
            onClick={() => run(startAcquisition("trading-calendar", true))}
          >
            刷新交易日历
          </Button>
          <div className="flex w-full gap-2 pt-2">
            <Input
              aria-label="单只股票代码"
              placeholder="输入股票代码，例如 000001"
              value={singleSymbol}
              onChange={(event) => setSingleSymbol(event.target.value)}
            />
            <Button
              disabled={running || !singleSymbol.trim()}
              variant="outline"
              onClick={() =>
                run(
                  startAcquisition("securities", true, {
                    symbols: [singleSymbol.trim()],
                  }),
                )
              }
            >
              刷新该股票
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>按范围同步策略数据</CardTitle>
          <CardDescription>
            多个股票代码使用英文逗号分隔。系统随机选择来源，失败时自动切换。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              const data = new FormData(event.currentTarget)
              const symbols = String(data.get("symbols"))
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean)
              void run(
                startAcquisition(syncDataset, true, {
                  symbols,
                  start_day: String(data.get("start_day")),
                  end_day: String(data.get("end_day")),
                }),
              )
            }}
          >
            <FieldGroup>
              <Field>
                <FieldLabel>数据集</FieldLabel>
                <Select value={syncDataset} onValueChange={setSyncDataset}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily-bars">日线 K 线</SelectItem>
                    <SelectItem value="market-values">估值与市值</SelectItem>
                    <SelectItem value="pledge-ratios">股票质押率</SelectItem>
                    <SelectItem value="financial-indicators">财务指标</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="symbols">股票代码</FieldLabel>
                <Input id="symbols" name="symbols" placeholder="000001,600000" required />
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field>
                  <FieldLabel htmlFor="start_day">开始日期</FieldLabel>
                  <Input id="start_day" name="start_day" type="date" required />
                </Field>
                <Field>
                  <FieldLabel htmlFor="end_day">结束日期</FieldLabel>
                  <Input id="end_day" name="end_day" type="date" required />
                </Field>
              </div>
            </FieldGroup>
            <Button type="submit" disabled={running}>
              {running ? "正在同步…" : "开始同步"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <p aria-live="polite">最近任务：{message}</p>
      {lastTask?.attempts?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>来源尝试明细</CardTitle>
            <CardDescription>成功后立即停止，不比较不同来源的数据。</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            {lastTask.attempts.map((attempt, index) => (
              <p className="break-words" key={`${attempt.source_key}-${attempt.attempt}-${index}`}>
                {attempt.source_key} · 第 {attempt.attempt || "缓存"} 次 ·{" "}
                {localizedLabel(attempt.status)}
                {attempt.message ? ` · ${attempt.message}` : ""}
              </p>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
