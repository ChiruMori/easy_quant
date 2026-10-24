import { Plus, X } from "lucide-react"
import { memo, useId, useMemo, useRef, useState } from "react"
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { IconButton } from "@/components/icon-button"
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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { apiRequest } from "@/lib/api/client"

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
}: {
  kind: "backtest" | "live"
  resourceId: string
  series: PortfolioSeries[]
  amountLabel?: string
  comparisonsEnabled?: boolean
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
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={unit}
          onValueChange={(value) => {
            if (value) setUnit(value)
          }}
          aria-label="图表显示单位"
        >
          <ToggleGroupItem value="amount" aria-label="金额（元）">
            ￥
          </ToggleGroupItem>
          <ToggleGroupItem value="return_rate" aria-label="收益率（%）">
            %
          </ToggleGroupItem>
        </ToggleGroup>
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
      <div
        role="img"
        aria-label={`${amountLabel}曲线，共 ${days.length} 个交易日，单位为${unit === "amount" ? "元" : "%"}`}
        className="h-72 w-full min-w-0"
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
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
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
})
