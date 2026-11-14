import { useQuery, useQueryClient } from "@tanstack/react-query"
import { lazy, Suspense, useMemo, useState } from "react"
import { Link, useLocation, useParams } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { DatePicker } from "@/components/date-picker"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"

import { getInstrument, getInstrumentDailyBars, updateInstrumentStatus } from "../api"
import { aggregateCandles, type CandlePeriod } from "../candles"
import { FinancialReportsPanel } from "../components/financial-reports-panel"
import { FundamentalsPanel } from "../components/fundamentals-panel"

const CandlestickChart = lazy(() =>
  import("../components/candlestick-chart").then((module) => ({
    default: module.CandlestickChart,
  })),
)

export function InstrumentDetailPage({ readOnly = false }: { readOnly?: boolean }) {
  const { symbol = "" } = useParams()
  const location = useLocation()
  const from: unknown = location.state?.from
  const returnTo =
    typeof from === "string" && from.startsWith("/") && !from.startsWith("//") ? from : "/backtests"
  const isIndex = /^(sh|sz)\d{6}$/i.test(symbol)
  const [range, setRange] = useState({ start: "", end: "" })
  const [appliedRange, setAppliedRange] = useState(range)
  const [period, setPeriod] = useState<CandlePeriod>("day")
  const [statusReason, setStatusReason] = useState("")
  const [statusMessage, setStatusMessage] = useState("")
  const [statusSaving, setStatusSaving] = useState(false)
  const queryClient = useQueryClient()
  const instrument = useQuery({
    queryKey: ["instrument", symbol],
    queryFn: () => getInstrument(symbol, readOnly),
  })
  const bars = useQuery({
    queryKey: ["instrument-bars", symbol, appliedRange],
    queryFn: () => getInstrumentDailyBars(symbol, appliedRange.start, appliedRange.end, readOnly),
  })
  const chartData = useMemo(() => aggregateCandles(bars.data ?? [], period), [bars.data, period])
  if (instrument.isLoading) return <LoadingState label="正在加载股票详情" />
  if (instrument.error)
    return <ErrorState title="无法加载股票详情" message={instrument.error.message} />
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1 basis-64">
          <h1 className="text-2xl font-semibold [overflow-wrap:anywhere]">
            {instrument.data?.symbol} {instrument.data?.name}
            {isIndex && <Badge variant="secondary">指数 · 不可交易</Badge>}
            {instrument.data?.status === "delisted" && (
              <Badge className="ml-2 align-middle" variant="secondary">
                已退市
              </Badge>
            )}
            {instrument.data?.status === "suspended" && (
              <Badge className="ml-2 align-middle" variant="secondary">
                已停牌
              </Badge>
            )}
          </h1>
          <p className="text-muted-foreground">
            {instrument.data?.exchange} · 上市日期 {instrument.data?.listed_on ?? "未知"}
          </p>
        </div>
        <Button variant="outline" asChild>
          <Link to={readOnly ? returnTo : isIndex ? "/admin/data?tab=indices" : "/admin/data"}>
            {readOnly ? "返回来源页面" : "返回数据列表"}
          </Link>
        </Button>
      </div>
      {!readOnly && !isIndex && instrument.data?.status !== "delisted" && (
        <Card>
          <CardHeader>
            <CardTitle>交易状态</CardTitle>
            <CardDescription>
              核实交易所公告后可标记停牌；停牌股票不再显示过期与更新按钮，历史 K 线仍保留。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="flex flex-col gap-3 sm:flex-row sm:items-end"
              onSubmit={(event) => {
                event.preventDefault()
                setStatusSaving(true)
                setStatusMessage("")
                const nextStatus = instrument.data?.status === "suspended" ? "active" : "suspended"
                void updateInstrumentStatus(symbol, nextStatus, statusReason.trim())
                  .then(() => {
                    setStatusReason("")
                    setStatusMessage(nextStatus === "suspended" ? "已标记停牌" : "已恢复交易状态")
                    return Promise.all([
                      queryClient.invalidateQueries({ queryKey: ["instrument", symbol] }),
                      queryClient.invalidateQueries({
                        queryKey: ["admin", "market-data", "coverage"],
                      }),
                    ])
                  })
                  .catch((error: unknown) => {
                    setStatusMessage(error instanceof Error ? error.message : "更新状态失败")
                  })
                  .finally(() => setStatusSaving(false))
              }}
            >
              <Field className="flex-1">
                <FieldLabel htmlFor="status-reason">状态依据</FieldLabel>
                <Input
                  id="status-reason"
                  value={statusReason}
                  onChange={(event) => setStatusReason(event.target.value)}
                  placeholder="例如：交易所停牌公告日期与编号"
                  minLength={4}
                  maxLength={500}
                  required
                />
              </Field>
              <Button type="submit" disabled={statusSaving}>
                {instrument.data?.status === "suspended" ? "恢复交易状态" : "标记停牌"}
              </Button>
            </form>
            {statusMessage && (
              <p className="mt-2 text-sm" aria-live="polite">
                {statusMessage}
              </p>
            )}
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>K 线图</CardTitle>
          <CardDescription>
            红涨绿跌；支持拖动和滚轮缩放。默认读取最近 180 条日线，指定范围最多读取 1,000
            条日线，周/月线由日线聚合。 默认叠加 MA5（5
            {period === "day" ? "日" : period === "week" ? "周" : "月"}收盘均线），从所选区间的第 5
            根 K 线开始绘制；点击图例可隐藏。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ToggleGroup
            type="single"
            value={period}
            onValueChange={(value) => {
              if (value) setPeriod(value as CandlePeriod)
            }}
            variant="outline"
            aria-label="K 线周期"
          >
            <ToggleGroupItem value="day">日 K</ToggleGroupItem>
            <ToggleGroupItem value="week">周 K</ToggleGroupItem>
            <ToggleGroupItem value="month">月 K</ToggleGroupItem>
          </ToggleGroup>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              setAppliedRange(range)
            }}
          >
            <FieldGroup className="sm:grid sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
              <Field>
                <FieldLabel htmlFor="bar-start">开始日期</FieldLabel>
                <DatePicker
                  id="bar-start"

                  value={range.start}
                  onValueChange={(dateValue) =>
                    setRange((value) => ({ ...value, start: dateValue }))
                  }
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="bar-end">结束日期</FieldLabel>
                <DatePicker
                  id="bar-end"

                  value={range.end}
                  onValueChange={(dateValue) => setRange((value) => ({ ...value, end: dateValue }))}
                />
              </Field>
              <Button type="submit">查询</Button>
            </FieldGroup>
          </form>
          {bars.isLoading ? (
            <LoadingState label="正在加载日线" />
          ) : bars.error ? (
            <div className="flex flex-col items-start gap-3">
              <ErrorState title="无法加载日线" message={bars.error.message} />
              <Button
                variant="outline"
                disabled={bars.isFetching}
                onClick={() => void bars.refetch()}
              >
                重试日线
              </Button>
            </div>
          ) : chartData.length ? (
            <Suspense fallback={<LoadingState label="正在加载 K 线图" />}>
              <CandlestickChart bars={chartData} period={period} />
            </Suspense>
          ) : (
            <p className="text-muted-foreground">所选范围内没有日线数据，请先同步该股票。</p>
          )}
        </CardContent>
      </Card>
      {!isIndex && (
        <>
          <FinancialReportsPanel key={`${symbol}-reports`} symbol={symbol} />
          <FinancialReportsPanel key={`${symbol}-business`} symbol={symbol} business />
          <FundamentalsPanel key={symbol} symbol={symbol} />
        </>
      )}
    </div>
  )
}
