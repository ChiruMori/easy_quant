import { useNavigate } from "react-router-dom"
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

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
import { startLive } from "@/features/live-tracking/api"
import { localizedLabel } from "@/lib/labels"

import type { Backtest } from "../api"
import { backtestStatusLabel, formatMetric, metricLabel } from "../format"

export function BacktestDetailPage({ run }: { run: Backtest }) {
  const navigate = useNavigate()
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">回测详情</h1>
          <p className="text-muted-foreground">
            状态：{backtestStatusLabel(run.status)}（{run.progress}%）
          </p>
        </div>
        <Button
          disabled={run.status !== "succeeded"}
          onClick={async () => {
            const live = await startLive(run.id, run.strategy_version_id)
            navigate(`/live/${live.id}`)
          }}
        >
          开启实盘跟踪
        </Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>回测指标</CardTitle>
          <CardDescription>策略历史模拟结果不代表未来收益。</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(run.metrics).map(([key, value]) => (
              <div key={key}>
                <dt className="text-sm text-muted-foreground">{metricLabel(key)}</dt>
                <dd
                  className="max-w-full truncate font-medium tabular-nums"
                  title={formatMetric(key, value)}
                >
                  {formatMetric(key, value)}
                </dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
      <div className="h-72">
        <ResponsiveContainer>
          <LineChart data={run.periods}>
            <XAxis dataKey="trading_day" />
            <YAxis />
            <Tooltip
              formatter={(value) =>
                Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 })
              }
            />
            <Line dataKey="equity" name="组合权益" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
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
