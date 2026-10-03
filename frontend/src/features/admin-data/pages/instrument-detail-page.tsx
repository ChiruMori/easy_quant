import { useQuery } from "@tanstack/react-query"
import { lazy, Suspense, useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"

import { getInstrument, getInstrumentDailyBars } from "../api"
import { aggregateCandles, type CandlePeriod } from "../candles"

const CandlestickChart = lazy(() =>
  import("../components/candlestick-chart").then((module) => ({
    default: module.CandlestickChart,
  })),
)

export function InstrumentDetailPage() {
  const { symbol = "" } = useParams()
  const [range, setRange] = useState({ start: "", end: "" })
  const [appliedRange, setAppliedRange] = useState(range)
  const [period, setPeriod] = useState<CandlePeriod>("day")
  const instrument = useQuery({
    queryKey: ["instrument", symbol],
    queryFn: () => getInstrument(symbol),
  })
  const bars = useQuery({
    queryKey: ["instrument-bars", symbol, appliedRange],
    queryFn: () => getInstrumentDailyBars(symbol, appliedRange.start, appliedRange.end),
  })
  const chartData = useMemo(() => aggregateCandles(bars.data ?? [], period), [bars.data, period])
  if (instrument.isLoading) return <LoadingState label="正在加载股票详情" />
  if (instrument.error)
    return <ErrorState title="无法加载股票详情" message={instrument.error.message} />
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">
            {instrument.data?.symbol} {instrument.data?.name}
          </h1>
          <p className="text-muted-foreground">
            {instrument.data?.exchange} · 上市日期 {instrument.data?.listed_on ?? "未知"}
          </p>
        </div>
        <Button variant="outline" asChild>
          <Link to="/admin/data">返回数据列表</Link>
        </Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>K 线图</CardTitle>
          <CardDescription>
            红涨绿跌；支持拖动和滚轮缩放。默认读取最近 180 条日线，指定范围最多读取 1,000
            条日线，周/月线由日线聚合。
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
            <FieldGroup className="sm:flex-row">
              <Field>
                <FieldLabel htmlFor="bar-start">开始日期</FieldLabel>
                <Input
                  id="bar-start"
                  type="date"
                  value={range.start}
                  onChange={(event) =>
                    setRange((value) => ({ ...value, start: event.target.value }))
                  }
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="bar-end">结束日期</FieldLabel>
                <Input
                  id="bar-end"
                  type="date"
                  value={range.end}
                  onChange={(event) => setRange((value) => ({ ...value, end: event.target.value }))}
                />
              </Field>
              <Button type="submit">查询</Button>
            </FieldGroup>
          </form>
          {bars.isLoading ? (
            <LoadingState label="正在加载日线" />
          ) : bars.error ? (
            <ErrorState title="无法加载日线" message={bars.error.message} />
          ) : chartData.length ? (
            <Suspense fallback={<LoadingState label="正在加载 K 线图" />}>
              <CandlestickChart bars={chartData} />
            </Suspense>
          ) : (
            <p className="text-muted-foreground">所选范围内没有日线数据，请先同步该股票。</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
