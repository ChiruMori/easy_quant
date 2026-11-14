import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { useAuthentication } from "@/app/providers"
import { ErrorState, LoadingState } from "@/components/app-shell"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import { getAcquisition, getReportSeries, startAcquisition } from "../api"
import { chartNumber, reportMetrics, reportPeriods, reportPoints } from "./report-data"

function Choice({
  label,
  value,
  onChange,
  choices,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  choices: { value: string; label: string }[]
}) {
  return (
    <Field className="min-w-0 flex-1 basis-40">
      <FieldLabel>{label}</FieldLabel>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger aria-label={label} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {choices.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </Field>
  )
}

function ValueChart({
  points,
  label,
  unit,
}: {
  points: { period: string; value: number | null }[]
  label: string
  unit: string
}) {
  return (
    <>
      <div
        className="h-72 w-full min-w-0"
        role="img"
        aria-label={`${label}报表图，单位${unit}，缺失值留空`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={points}
            margin={{ top: 12, right: 12, bottom: 12, left: 0 }}
            accessibilityLayer
          >
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              minTickGap={20}
            />
            <YAxis width={56} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
            <Tooltip
              contentStyle={{
                background: "var(--card)",
                color: "var(--card-foreground)",
                borderColor: "var(--border)",
              }}
              formatter={(value: number) => [
                value.toLocaleString("zh-CN", { maximumFractionDigits: 4 }),
                `${label}（${unit}）`,
              ]}
            />
            <Bar
              dataKey="value"
              name={label}
              fill="var(--primary)"
              radius={[3, 3, 0, 0]}
              maxBarSize={48}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details>
        <summary className="cursor-pointer text-sm">查看图表数值与缺失项</summary>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>报告期 / 项目</TableHead>
              <TableHead>
                {label}（{unit}）
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {points.map((point) => (
              <TableRow key={point.period}>
                <TableCell className="max-w-48 break-words whitespace-normal">
                  {point.period}
                </TableCell>
                <TableCell>
                  {point.value === null
                    ? "数据缺失"
                    : point.value.toLocaleString("zh-CN", { maximumFractionDigits: 4 })}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </details>
    </>
  )
}

export function FinancialReportsPanel({
  symbol,
  business = false,
}: {
  symbol: string
  business?: boolean
}) {
  const { user } = useAuthentication()
  const [metric, setMetric] = useState("parent_net_profit")
  const [source, setSource] = useState("")
  const [reportFilter, setReportFilter] = useState("12-31")
  const [selectedPeriod, setSelectedPeriod] = useState("")
  const [category, setCategory] = useState("")
  const [businessMetric, setBusinessMetric] = useState("business_revenue")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [taskId, setTaskId] = useState("")
  const client = useQueryClient()
  const info = reportMetrics[metric as keyof typeof reportMetrics]
  const dataset = business ? "business-compositions" : info.dataset
  const reports = useQuery({
    queryKey: ["report-series", symbol, dataset, source],
    queryFn: () => getReportSeries(symbol, dataset, source),
  })
  const task = useQuery({
    queryKey: ["report-acquisition", taskId],
    queryFn: async () => {
      const result = await getAcquisition(taskId)
      if (result.status === "succeeded" || result.status === "failed") {
        await Promise.all([
          client.invalidateQueries({ queryKey: ["report-series", symbol] }),
          client.invalidateQueries({ queryKey: ["instrument-fundamentals", symbol] }),
          client.invalidateQueries({ queryKey: ["instrument-records", symbol] }),
        ])
      }
      return result
    },
    enabled: Boolean(taskId),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "queued") ? 2000 : false,
  })
  const periods = useMemo(() => reportPeriods(reports.data?.as_of ?? ""), [reports.data?.as_of])
  const rows = reports.data?.items ?? []
  const latestAvailable = rows
    .map((row) => row.report_period ?? "")
    .sort()
    .at(-1)
  const period = selectedPeriod || (business ? latestAvailable : "") || periods.at(-1) || ""
  const periodRows = rows.filter((row) => row.report_period === period)
  const categories = [...new Set(periodRows.map((row) => String(row.category ?? "未分类")))].sort()
  const activeCategory = categories.includes(category) ? category : (categories[0] ?? "")
  const businessFields = [
    { value: "business_revenue", label: "主营收入" },
    { value: "business_cost", label: "主营成本" },
    { value: "business_profit", label: "主营利润" },
  ]
  const label = business
    ? businessFields.find((item) => item.value === businessMetric)!.label
    : info.label
  const points = business
    ? periodRows
        .filter((row) => String(row.category ?? "未分类") === activeCategory)
        .map((row) => ({
          period: String(row.item_name ?? "未命名项目"),
          value: chartNumber(row[businessMetric]),
        }))
    : reportPoints(
        rows,
        periods.filter((period) => reportFilter === "all" || period.endsWith(reportFilter)),
        metric,
        info.scale,
      )
  const missing = points.filter((point) => point.value === null)
  const canSubmit =
    !busy &&
    !(taskId && !task.data) &&
    !["queued", "running"].includes(task.data?.status ?? "") &&
    !task.isError
  async function acquire() {
    setBusy(true)
    setError("")
    try {
      const result = await startAcquisition(dataset, true, {
        symbols: [symbol],
        start_day: period,
        end_day: period,
      })
      setTaskId(result.id)
    } catch (error) {
      setError(error instanceof Error ? error.message : "提交补采失败")
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>{business ? "主营与构成报表" : "财务报表分析"}</CardTitle>
        <CardDescription>
          {business
            ? "按报告期和分类比较主营收入、成本与利润；不同分类不混加，不推算未披露项目。"
            : "近五年合并报表，每个报告期取所选来源当前可见版本。利润与现金流为年初累计，不叠加季度；缺失留空。"}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex min-w-0 flex-col gap-4">
        <div className="flex min-w-0 flex-wrap items-end gap-3">
          <Choice
            label={business ? "主营指标" : "财务指标"}
            value={business ? businessMetric : metric}
            onChange={
              business
                ? setBusinessMetric
                : (value) => {
                    setMetric(value)
                    setSource("")
                  }
            }
            choices={
              business
                ? businessFields
                : Object.entries(reportMetrics).map(([value, item]) => ({
                    value,
                    label: item.label,
                  }))
            }
          />
          {!business && (
            <Choice
              label="报告类型"
              value={reportFilter}
              onChange={setReportFilter}
              choices={[
                { value: "12-31", label: "年报" },
                { value: "03-31", label: "一季报" },
                { value: "06-30", label: "中报" },
                { value: "09-30", label: "三季报" },
                { value: "all", label: "全部报告（累计）" },
              ]}
            />
          )}
          {!!reports.data?.sources.length && (
            <Choice
              label={business ? "主营来源" : "财报来源"}
              value={source || reports.data.source}
              onChange={setSource}
              choices={reports.data.sources.map((value) => ({
                value,
                label: value === "eastmoney" ? "东方财富" : value === "sina" ? "新浪财经" : value,
              }))}
            />
          )}
          {(business || user?.role === "admin") && periods.length > 0 && (
            <Choice
              label={business ? "主营报告期" : "补采报告期"}
              value={period}
              onChange={setSelectedPeriod}
              choices={[...periods].reverse().map((value) => ({ value, label: value }))}
            />
          )}
          {business && categories.length > 0 && (
            <Choice
              label="构成分类"
              value={activeCategory}
              onChange={setCategory}
              choices={categories.map((value) => ({
                value,
                label:
                  ({ "1": "按行业", "2": "按产品", "3": "按地区" } as Record<string, string>)[
                    value
                  ] ?? value,
              }))}
            />
          )}
        </div>
        {reports.isLoading ? (
          <LoadingState label="正在加载报表图表" />
        ) : reports.error ? (
          <>
            <ErrorState title="无法加载报表图表" message={reports.error.message} />
            <Button variant="outline" onClick={() => void reports.refetch()}>
              重试报表图表
            </Button>
          </>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              {label} · {business ? "亿元" : info.unit} ·{" "}
              {business ? period : "报告期累计 / 时点口径"} ·{" "}
              {missing.length ? `${missing.length} 项数据缺失` : "缺失项目以空白表示"}
            </p>
            {points.some((point) => point.value !== null) ? (
              <ValueChart points={points} label={label} unit={business ? "亿元" : info.unit} />
            ) : (
              <p className="text-muted-foreground">
                所选报告暂无可展示数据，缺失值不补零。
                {business ? "可切换报告期检查已披露构成。" : "可切换指标或报告类型。"}
              </p>
            )}
          </>
        )}
        {user?.role === "admin" && period && (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" disabled={!canSubmit} onClick={() => void acquire()}>
              {busy ? "正在提交补采" : `补采${business ? "主营" : "财报"} ${period}`}
            </Button>
            <span className="text-sm text-muted-foreground">
              仅采集 {symbol} 所选数据集与报告期，后台串行执行。
            </span>
          </div>
        )}
        {(error || task.error) && (
          <Alert variant="destructive">
            <AlertDescription>
              <p>{error || task.error?.message}</p>
              {taskId && (
                <Button variant="outline" onClick={() => void task.refetch()}>
                  重试任务状态
                </Button>
              )}
            </AlertDescription>
          </Alert>
        )}
        {task.data && (
          <Alert variant={task.data.status === "failed" ? "destructive" : "default"}>
            <AlertDescription>
              {["queued", "running"].includes(task.data.status)
                ? "补采任务已提交，正在等待处理。"
                : task.data.status === "failed"
                  ? `补采部分失败，成功数据已保留：${task.data.message ?? "请重试"}`
                  : `补采完成，保存 ${task.data.record_count ?? 0} 条。`}
              <a href="/admin/jobs" className="underline">
                查看后台任务
              </a>
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
