import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

import { getInstrument, getInstrumentDailyBars } from "../api"
import type { DailyBar } from "../types"

type CandleProps = {
  x?: number
  y?: number
  width?: number
  height?: number
  payload?: DailyBar & { range: [number, number] }
}

function Candle({ x = 0, y = 0, width = 0, height = 0, payload }: CandleProps) {
  if (!payload) return null
  const high = Number(payload.high)
  const low = Number(payload.low)
  const open = Number(payload.open)
  const close = Number(payload.close)
  const scale = high === low ? 0 : height / (high - low)
  const bodyTop = y + (high - Math.max(open, close)) * scale
  const bodyHeight = Math.max(1, Math.abs(open - close) * scale)
  const color = close >= open ? "var(--chart-2)" : "var(--destructive)"
  const center = x + width / 2
  return (
    <g>
      <line x1={center} x2={center} y1={y} y2={y + height} stroke={color} />
      <rect x={x + width * 0.2} y={bodyTop} width={width * 0.6} height={bodyHeight} fill={color} />
    </g>
  )
}

export function InstrumentDetailPage() {
  const { symbol = "" } = useParams()
  const [range, setRange] = useState({ start: "", end: "" })
  const [appliedRange, setAppliedRange] = useState(range)
  const instrument = useQuery({
    queryKey: ["instrument", symbol],
    queryFn: () => getInstrument(symbol),
  })
  const bars = useQuery({
    queryKey: ["instrument-bars", symbol, appliedRange],
    queryFn: () => getInstrumentDailyBars(symbol, appliedRange.start, appliedRange.end),
  })
  if (instrument.isLoading) return <LoadingState label="正在加载股票详情" />
  if (instrument.error)
    return <ErrorState title="无法加载股票详情" message={instrument.error.message} />
  const chartData = (bars.data ?? []).map((item) => ({
    ...item,
    range: [Number(item.low), Number(item.high)] as [number, number],
  }))
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
          <CardTitle>日线 K 线</CardTitle>
          <CardDescription>默认展示最近 180 条；指定日期范围时最多返回 1,000 条。</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
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
            <div className="h-[420px] w-full">
              <ResponsiveContainer>
                <BarChart data={chartData} margin={{ left: 8, right: 8 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="trading_day" minTickGap={32} />
                  <YAxis domain={["dataMin", "dataMax"]} width={72} />
                  <Tooltip
                    content={({ active, payload }) =>
                      active && payload?.[0] ? (
                        <div className="rounded-md border bg-background p-2 text-xs shadow">
                          <p>{String(payload[0].payload.trading_day)}</p>
                          <p>
                            开 {String(payload[0].payload.open)} · 高{" "}
                            {String(payload[0].payload.high)}
                          </p>
                          <p>
                            低 {String(payload[0].payload.low)} · 收{" "}
                            {String(payload[0].payload.close)}
                          </p>
                        </div>
                      ) : null
                    }
                  />
                  <Bar dataKey="range" shape={<Candle />} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-muted-foreground">所选范围内没有日线数据，请先同步该股票。</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
