import Decimal from "decimal.js"
import { useState } from "react"

import { EmptyState } from "@/components/app-shell"
import { MetricCard } from "@/components/metric-card"
import { PageHeader } from "@/components/page-header"
import { PortfolioChart, type PortfolioSeries } from "@/components/portfolio-chart"
import { executionStageLabel, RunTimingPanel } from "@/components/run-timing"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { StartLivePage } from "@/features/live-tracking/pages/start-live-page"
import { StrategyPreview } from "@/features/strategies/components/strategy-preview"
import { localizedLabel } from "@/lib/labels"

import type { Backtest } from "../api"
import { RenameBacktest } from "../components/rename-backtest"
import { StockPerformanceTable } from "../components/stock-performance-table"
import { backtestStatusLabel, formatMetric, metricLabel } from "../format"

export function BacktestDetailPage({ run }: { run: Backtest }) {
  const [configureLive, setConfigureLive] = useState(false)
  const [renamed, setRenamed] = useState<string>()
  const name = renamed ?? run.name
  const initial = new Decimal(run.config?.initial_cash ?? run.periods[0]?.equity ?? "1")
  const series: PortfolioSeries[] = [
    {
      id: `backtest:${run.id}`,
      name: "组合权益",
      points: run.periods.map((point) => ({
        day: point.trading_day,
        amount: point.equity,
        return_rate: initial.gt(0)
          ? new Decimal(point.equity).div(initial).minus(1).toFixed()
          : null,
      })),
    },
  ]
  if (run.benchmark)
    series.push({
      id: `instrument:${run.benchmark.symbol}`,
      name: run.benchmark.name,
      points: run.periods.map((point) => ({
        day: point.trading_day,
        amount: point.benchmark_equity ?? null,
        return_rate:
          point.benchmark_equity !== null && point.benchmark_equity !== undefined && initial.gt(0)
            ? new Decimal(point.benchmark_equity).div(initial).minus(1).toFixed()
            : null,
      })),
    })
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={name ? `回测详情 · ${name}` : "回测详情"}
        description={`状态：${backtestStatusLabel(run.status)}（${run.progress}%）`}
        actions={
          <>
            <RenameBacktest id={run.id} name={name} onSaved={setRenamed} />
            <Button
              disabled={run.status !== "succeeded"}
              onClick={() => setConfigureLive((value) => !value)}
            >
              开启实盘跟踪
            </Button>
          </>
        }
      />
      <StrategyPreview strategy={run.strategy} versionId={run.strategy_version_id} />
      {configureLive && (
        <StartLivePage
          backtestId={run.id}
          strategyVersionId={run.strategy_version_id}
          parameters={run.config?.parameters}
        />
      )}
      {run.benchmark && (
        <p className="text-sm text-muted-foreground">
          基准：{run.benchmark.name}（{run.benchmark.symbol}），以区间首个交易日收盘为基点。
        </p>
      )}
      {run.assumptions.intraday_quote && (
        <p className="text-sm text-muted-foreground">
          盘中模拟报价为当日开收盘均值，包含收盘信息，只代表日线近似模拟。
        </p>
      )}
      {["queued", "running"].includes(run.status) && (
        <Alert>
          <AlertTitle>回测已进入后台任务</AlertTitle>
          <AlertDescription>
            {run.job_id
              ? `任务 ${run.job_id} 正在${run.status === "queued" ? "排队" : "运行"}`
              : "正在处理"}
            ，页面会自动刷新。
            {run.execution && (
              <p role="status">
                {executionStageLabel(run.execution.stage)}
                {run.execution.trading_day && ` · ${run.execution.trading_day}`}
                {run.execution.hook && ` · ${run.execution.hook}`}
                {run.execution.elapsed_seconds !== undefined &&
                  ` · 已用 ${run.execution.elapsed_seconds.toFixed(1)} 秒`}
              </p>
            )}
          </AlertDescription>
        </Alert>
      )}
      {run.status === "failed" && (
        <Alert variant="destructive">
          <AlertTitle>回测失败</AlertTitle>
          <AlertDescription>
            {run.error ?? "请在后台任务中查看失败原因。"}
            {run.error_details?.action_url && (
              <a href={run.error_details.action_url} className="underline">
                前往数据管理补齐数据
              </a>
            )}
            {run.error_details?.missing_data && (
              <div className="max-h-64 overflow-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>标的</TableHead>
                      <TableHead>需要区间</TableHead>
                      <TableHead>已同步区间</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {run.error_details.missing_data.map((item, index) => (
                      <TableRow key={index}>
                        <TableCell>{item.symbol}</TableCell>
                        <TableCell>
                          {item.start_day} 至 {item.end_day}
                        </TableCell>
                        <TableCell>
                          {item.available_start} 至 {item.available_end}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </AlertDescription>
        </Alert>
      )}
      <section aria-label="回测指标" className="flex flex-col gap-3">
        <div>
          <h2 className="text-base font-semibold">回测指标</h2>
          <p className="mt-1 text-sm text-muted-foreground">策略历史模拟结果不代表未来收益。</p>
        </div>
        {Object.keys(run.metrics).length ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Object.entries(run.metrics).map(([key, value]) => (
              <MetricCard
                key={key}
                label={metricLabel(key)}
                value={formatMetric(key, value)}
                tone={
                  ["cumulative_return", "annualized_return", "benchmark_return"].includes(key) &&
                  value !== null
                    ? Number(value) > 0
                      ? "up"
                      : Number(value) < 0
                        ? "down"
                        : "neutral"
                    : "neutral"
                }
              />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent>
              <EmptyState title="尚无回测指标" message="该记录尚未生成可展示的指标。" />
            </CardContent>
          </Card>
        )}
      </section>
      {run.periods.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>组合权益</CardTitle>
            <CardDescription>
              按交易日展示模拟组合，可切换金额或收益率；新增对比仅当前页面有效。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PortfolioChart key={run.id} kind="backtest" resourceId={run.id} series={series} />
          </CardContent>
        </Card>
      )}
      <RunTimingPanel timing={run.timing} />
      {run.status === "succeeded" && <StockPerformanceTable key={run.id} runId={run.id} />}
      <Card>
        <CardHeader>
          <CardTitle>交易与假设披露</CardTitle>
          <CardDescription>{run.trades.length} 笔模拟交易</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <dl className="grid gap-3 rounded-md bg-muted p-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">数据频率</dt>
              <dd>日线</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">手续费率</dt>
              <dd className="tabular-nums">{formatMetric("turnover", run.assumptions.fee_rate)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">滑点率</dt>
              <dd className="tabular-nums">
                {formatMetric("turnover", run.assumptions.slippage_rate)}
              </dd>
            </div>
          </dl>
          <div className="overflow-x-auto">
            <Table className="min-w-[720px]">
              <TableHeader>
                <TableRow>
                  <TableHead>交易日</TableHead>
                  <TableHead>股票</TableHead>
                  <TableHead>动作</TableHead>
                  <TableHead className="text-right">数量</TableHead>
                  <TableHead className="text-right">价格</TableHead>
                  <TableHead className="text-right">费用</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {run.trades.map((trade, index) => (
                  <TableRow key={`${trade.trading_day}-${trade.symbol}-${index}`}>
                    <TableCell>{trade.trading_day}</TableCell>
                    <TableCell>{trade.symbol}</TableCell>
                    <TableCell>{localizedLabel(trade.action)}</TableCell>
                    <TableCell className="text-right tabular-nums">{trade.quantity}</TableCell>
                    <TableCell className="text-right tabular-nums">{trade.price}</TableCell>
                    <TableCell className="text-right tabular-nums">{trade.fee}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-sm break-all text-muted-foreground">
            快照 {run.snapshot_id} · 应用 {run.application_version}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
