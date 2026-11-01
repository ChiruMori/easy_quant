import { Plus, X } from "lucide-react"
import { memo, useId, useMemo, useRef, useState } from "react"
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { IconButton } from "@/components/icon-button"
import { InstrumentLink } from "@/components/instrument-link"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip as Hint, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { apiRequest } from "@/lib/api/client"
import { formatMoney } from "@/lib/finance"

export interface PortfolioTrade {
  day: string
  action: string
  symbol: string
  quantity: string
  price: string
}

export function groupTradeMarkers(trades: PortfolioTrade[], points: PortfolioSeries["points"]) {
  const days = new Set(
    points
      .filter((point) => point.amount !== null || point.return_rate !== null)
      .map((point) => point.day),
  )
  const groups = new Map<string, { day: string; action: string; trades: PortfolioTrade[] }>()
  for (const trade of trades) {
    if (!days.has(trade.day) || !["buy", "sell"].includes(trade.action)) continue
    const key = `${trade.day}:${trade.action}`
    const group = groups.get(key) ?? { day: trade.day, action: trade.action, trades: [] }
    group.trades.push(trade)
    groups.set(key, group)
  }
  return [...groups.values()]
}

export interface PortfolioSeries {
  id: string
  name: string
  points: Array<{ day: string; amount: string | null; return_rate: string | null }>
}
export const PortfolioChart = memo(function PortfolioChart({
  kind,
  resourceId,
  series,
  amountLabel = "组合权益",
  comparisonsEnabled = true,
  trades = [],
}: {
  kind: "backtest" | "live"
  resourceId: string
  series: PortfolioSeries[]
  amountLabel?: string
  comparisonsEnabled?: boolean
  trades?: PortfolioTrade[]
}) {
  const gradient = useId()
  const [unit, setUnit] = useState("amount")
  const [extra, setExtra] = useState<PortfolioSeries[]>([])
  const [open, setOpen] = useState(false)
  const [source, setSource] = useState("instrument")
  const [search, setSearch] = useState("")
  const [results, setResults] = useState<Array<{ id: string; name: string }>>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const sending = useRef(false)
  const { curves, days, data } = useMemo(() => {
    const curves = [...series, ...extra]
    const days = [
      ...new Set(curves.flatMap((item) => item.points.map((point) => point.day))),
    ].sort()
    const indexed = curves.map((item) => new Map(item.points.map((point) => [point.day, point])))
    const data = days.map((day) =>
      Object.fromEntries([
        ["day", day],
        ...curves.map((_, index) => {
          const value = indexed[index].get(day)?.[unit === "amount" ? "amount" : "return_rate"]
          return [
            `line${index}`,
            value === null || value === undefined
              ? null
              : Number(value) * (unit === "amount" ? 1 : 100),
          ]
        }),
      ]),
    )
    return { curves, days, data }
  }, [series, extra, unit])
  const markers = useMemo(
    () => groupTradeMarkers(trades, series[0]?.points ?? []),
    [trades, series],
  )
  const pairedDays = useMemo(() => {
    const buys = new Set(
      markers.filter((marker) => marker.action === "buy").map((marker) => marker.day),
    )
    return new Set(
      markers
        .filter((marker) => marker.action === "sell" && buys.has(marker.day))
        .map((marker) => marker.day),
    )
  }, [markers])
  async function find() {
    if (sending.current) return
    sending.current = true
    setBusy(true)
    setError("")
    setResults([])
    try {
      const url =
        source === "instrument"
          ? "/chart-comparisons/instruments"
          : `/chart-comparisons/backtest/${resourceId}/candidates`
      setResults(
        (
          await apiRequest<Array<{ id: string; name: string }>>(
            `${url}?${new URLSearchParams({ search })}`,
          )
        ).slice(0, 20),
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "搜索失败，请重试")
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Tabs value={unit} onValueChange={setUnit}>
          <TabsList size="sm" aria-label="图表显示单位">
            <TabsTrigger value="amount" aria-label="金额（元）">
              ￥
            </TabsTrigger>
            <TabsTrigger value="return_rate" aria-label="收益率（%）">
              %
            </TabsTrigger>
          </TabsList>
        </Tabs>
        {comparisonsEnabled && (
          <Popover
            open={open}
            onOpenChange={(value) => {
              if (!busy) setOpen(value)
            }}
          >
            <PopoverTrigger asChild>
              <IconButton
                icon={Plus}
                label="添加对比"
                size="icon-sm"
                disabled={extra.length >= 8}
              />
            </PopoverTrigger>
            <PopoverContent
              className="flex max-h-[75dvh] w-80 max-w-[calc(100vw-2rem)] flex-col gap-3 overflow-y-auto"
              align="start"
            >
              <p className="font-medium">添加临时对比</p>
              {kind === "backtest" && (
                <Select
                  value={source}
                  disabled={busy}
                  onValueChange={(value) => {
                    setSource(value)
                    setResults([])
                    setError("")
                  }}
                >
                  <SelectTrigger aria-label="对比来源">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="instrument">指数 / 股票</SelectItem>
                      <SelectItem value="backtest">相同配置的回测</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              )}
              <form
                className="flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault()
                  void find()
                }}
              >
                <Input
                  aria-label="搜索对比对象"
                  value={search}
                  disabled={busy}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={source === "instrument" ? "代码或名称，如沪深300" : "回测名称或编号"}
                />
                <Button type="submit" disabled={busy}>
                  搜索
                </Button>
              </form>
              <p className="text-xs text-muted-foreground">
                仅当前页面展示，最多添加 8 条；市场金额按相同初始权益归一，使用已发布收盘价。
                {source === "backtest" && "仅列出起止日期、初始资金及持仓相同的已完成回测。"}
              </p>
              {busy && <p role="status">正在加载…</p>}
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              {!busy && !results.length && (
                <p className="text-sm text-muted-foreground">
                  搜索后选择对象；没有匹配时请调整关键词或补齐行情。
                </p>
              )}
              {results.map((result) => (
                <Button
                  key={result.id}
                  className="w-full min-w-0 justify-start"
                  title={result.name || result.id}
                  variant="outline"
                  disabled={busy || curves.some((item) => item.id === `${source}:${result.id}`)}
                  onClick={async () => {
                    if (sending.current) return
                    sending.current = true
                    setBusy(true)
                    setError("")
                    try {
                      const value = await apiRequest<PortfolioSeries>(
                        `/chart-comparisons/${kind}/${resourceId}/series?${new URLSearchParams({ [source === "instrument" ? "symbol" : "backtest_id"]: result.id })}`,
                      )
                      setExtra((previous) =>
                        previous.some((item) => item.id === value.id)
                          ? previous
                          : [...previous, value],
                      )
                      setOpen(false)
                    } catch (caught) {
                      setError(caught instanceof Error ? caught.message : "添加失败，请重试")
                    } finally {
                      sending.current = false
                      setBusy(false)
                    }
                  }}
                >
                  <span className="min-w-0 truncate">
                    {source === "backtest"
                      ? Array.from(result.name || result.id)
                          .slice(0, 20)
                          .join("") + (Array.from(result.name || result.id).length > 20 ? "…" : "")
                      : `${result.name} · ${result.id}`}
                  </span>
                </Button>
              ))}
            </PopoverContent>
          </Popover>
        )}
        {extra.map((item) => (
          <Badge key={item.id} variant="secondary" className="h-8 min-w-0 gap-1 px-2">
            <span className="max-w-40 truncate">{item.name}</span>
            <IconButton
              icon={X}
              label={`移除对比 ${item.name}`}
              size="icon"
              variant="ghost"
              className="size-5 rounded-full"
              onClick={() => setExtra((previous) => previous.filter((row) => row.id !== item.id))}
            />
          </Badge>
        ))}
      </div>
      {markers.length > 0 && (
        <p className="text-xs text-muted-foreground">
          红色 B · 买入 / 蓝色 S · 卖出（{kind === "live" ? "已记录的实际成交" : "模拟成交"}
          ；同日同方向合并，悬停或聚焦查看）
        </p>
      )}
      <div
        role="img"
        aria-label={`${amountLabel}曲线，共 ${days.length} 个交易日，单位为${unit === "amount" ? "元" : "%"}`}
        className="h-72 w-full min-w-0"
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 24, right: 20, bottom: 8, left: 0 }}>
            <defs>
              <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.16} />
                <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.01} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey="day"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
              tickMargin={12}
              minTickGap={45}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              width={65}
              tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
              tickFormatter={(value: number) =>
                unit === "return_rate"
                  ? `${value.toFixed(1)}%`
                  : Math.abs(value) >= 10000
                    ? `${(value / 10000).toFixed(1)}万`
                    : value.toLocaleString("zh-CN")
              }
            />
            <Tooltip
              contentStyle={{
                background: "var(--popover)",
                color: "var(--popover-foreground)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(value, name) => [
                `${Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} ${unit === "amount" ? "元" : "%"}`,
                name,
              ]}
            />
            <Legend />
            {curves.map((item, index) =>
              index === 0 ? (
                <Area
                  key={item.id}
                  dataKey={`line${index}`}
                  name={unit === "amount" ? amountLabel : "组合收益率"}
                  type="linear"
                  stroke="var(--chart-1)"
                  strokeWidth={2}
                  fill={`url(#${gradient})`}
                  dot={days.length === 1}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              ) : (
                <Line
                  key={item.id}
                  dataKey={`line${index}`}
                  name={item.name}
                  stroke={`var(--chart-${(index % 5) + 1})`}
                  strokeDasharray={index >= 5 ? "5 3" : undefined}
                  strokeWidth={2}
                  dot={days.length === 1}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              ),
            )}
            {markers.map((marker) => {
              const value = data.find((point) => point.day === marker.day)?.line0
              if (typeof value !== "number" || !Number.isFinite(value)) return null
              const buy = marker.action === "buy"
              const paired = pairedDays.has(marker.day)
              const label = `${marker.day} ${buy ? "买入 B" : "卖出 S"}，${marker.trades.length} 笔${kind === "live" ? "实际" : "模拟"}成交`
              return (
                <ReferenceDot
                  key={`${marker.day}:${marker.action}`}
                  x={marker.day}
                  y={value}
                  ifOverflow="visible"
                  shape={({ cx, cy }: { cx?: number; cy?: number }) => (
                    <Hint>
                      <TooltipTrigger asChild>
                        <g
                          tabIndex={0}
                          role="graphics-symbol"
                          aria-label={label}
                          data-trade-marker={marker.action}
                          data-marker-day={marker.day}
                          className="cursor-help outline-none focus:stroke-foreground"
                        >
                          {paired ? (
                            <path
                              d={`M ${cx} ${(cy ?? 0) - 4} A 4 4 0 0 ${buy ? 0 : 1} ${cx} ${(cy ?? 0) + 4} Z`}
                              fill={buy ? "#ef4444" : "#3b82f6"}
                              stroke="var(--background)"
                              strokeWidth={1}
                            />
                          ) : (
                            <circle
                              cx={cx}
                              cy={cy}
                              r={4}
                              fill={buy ? "#ef4444" : "#3b82f6"}
                              stroke="var(--background)"
                              strokeWidth={1}
                            />
                          )}
                          <text
                            x={(cx ?? 0) + (paired ? (buy ? -7 : 7) : 0)}
                            y={(cy ?? 0) - 10}
                            textAnchor="middle"
                            fill={buy ? "#ef4444" : "#3b82f6"}
                            fontSize={11}
                            fontWeight={700}
                          >
                            {buy ? "B" : "S"}
                          </text>
                        </g>
                      </TooltipTrigger>
                      <TooltipContent className="max-h-60 max-w-72 overflow-y-auto">
                        <p>{label}</p>
                        {marker.trades.map((trade, index) => (
                          <p key={index}>
                            <InstrumentLink symbol={trade.symbol} /> · {trade.quantity} 股 ·{" "}
                            {formatMoney(trade.price)} 元
                          </p>
                        ))}
                      </TooltipContent>
                    </Hint>
                  )}
                />
              )
            })}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
})
