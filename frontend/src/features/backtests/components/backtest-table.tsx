import { Link } from "react-router-dom"

import { EmptyState } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import type { Backtest } from "../api"
import { backtestStatusLabel, formatMetric } from "../format"

export function BacktestTable({ runs }: { runs: Backtest[] }) {
  if (!runs.length)
    return <EmptyState title="尚无回测记录" message="确认所需行情已同步后，创建回测来验证策略。" />
  return (
    <Table className="min-w-[600px]">
      <TableHeader>
        <TableRow>
          <TableHead>回测记录 / 策略版本</TableHead>
          <TableHead>状态</TableHead>
          <TableHead>创建时间</TableHead>
          <TableHead className="text-right">累计收益率</TableHead>
          <TableHead className="text-right">最大回撤</TableHead>
          <TableHead className="text-right">交易次数</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => (
          <TableRow key={run.id}>
            <TableCell>
              <Link
                className="block max-w-48 truncate font-medium text-primary underline-offset-4 hover:underline"
                to={`/backtests/${run.id}`}
                title={run.name || run.id}
              >
                {run.name || run.id}
              </Link>
              <p
                className="mt-1 max-w-48 truncate text-xs text-muted-foreground"
                title={run.strategy_version_id}
              >
                {run.strategy_version_id}
              </p>
            </TableCell>
            <TableCell>
              <Badge
                variant={
                  run.status === "succeeded"
                    ? "success"
                    : run.status === "failed"
                      ? "destructive"
                      : ["queued", "running", "snapshotting"].includes(run.status)
                        ? "info"
                        : "secondary"
                }
              >
                {backtestStatusLabel(run.status)}
              </Badge>
            </TableCell>
            <TableCell>
              {run.created_at
                ? new Date(run.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })
                : "未记录"}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {formatMetric("cumulative_return", run.metrics.cumulative_return ?? null)}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {formatMetric("max_drawdown", run.metrics.max_drawdown ?? null)}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {formatMetric("trade_count", run.metrics.trade_count ?? null)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
