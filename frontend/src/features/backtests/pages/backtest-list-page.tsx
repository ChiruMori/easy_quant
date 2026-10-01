import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
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

import { listBacktests } from "../api"
import { backtestStatusLabel, formatMetric } from "../format"

export function BacktestListPage() {
  const query = useQuery({ queryKey: ["backtests"], queryFn: listBacktests })
  if (query.isLoading) return <LoadingState label="正在加载回测记录" />
  if (query.error) return <ErrorState title="无法加载回测记录" message={query.error.message} />
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between">
        <div>
          <CardTitle>回测记录</CardTitle>
          <CardDescription>历史回测结果按策略版本和数据快照保存。</CardDescription>
        </div>
        <Button asChild>
          <Link to="/backtests/new">创建回测</Link>
        </Button>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {query.data?.length ? (
          <Table className="min-w-[720px]">
            <TableHeader>
              <TableRow>
                <TableHead>记录</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>累计收益率</TableHead>
                <TableHead>最大回撤</TableHead>
                <TableHead>交易次数</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.map((run) => (
                <TableRow key={run.id}>
                  <TableCell>
                    <Link
                      className="font-medium underline-offset-4 hover:underline"
                      to={`/backtests/${run.id}`}
                    >
                      {run.id}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{backtestStatusLabel(run.status)}</Badge>
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {formatMetric("cumulative_return", run.metrics.cumulative_return)}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {formatMetric("max_drawdown", run.metrics.max_drawdown)}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {formatMetric("trade_count", run.metrics.trade_count)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-muted-foreground">
            尚无回测记录。请先确认所需行情已同步，再创建回测。
          </p>
        )}
      </CardContent>
    </Card>
  )
}
