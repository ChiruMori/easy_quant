import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { EmptyState } from "@/components/app-shell"
import { ListPagination } from "@/components/list-pagination"
import { Alert, AlertDescription } from "@/components/ui/alert"
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
import { formatMoney, profitTone } from "@/lib/finance"
import { cn } from "@/lib/utils"

import { getStockPerformance } from "../api"

export function StockPerformanceTable({ runId }: { runId: string }) {
  const [page, setPage] = useState(1)
  const query = useQuery({
    queryKey: ["stock-performance", runId, page],
    queryFn: () => getStockPerformance(runId, page),
  })
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>股票收益明细</CardTitle>
        <CardDescription>
          按总收益从高到低排列；移动平均成本包含买入费用，已实现收益扣除卖出费用，浮动收益按回测期末收盘估值。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex min-w-0 flex-col gap-4">
        {query.isFetching && <p role="status">正在加载股票收益…</p>}
        {query.error && (
          <Alert variant="destructive">
            <AlertDescription>
              {query.error.message}
              <Button variant="link" onClick={() => void query.refetch()}>
                重试
              </Button>
            </AlertDescription>
          </Alert>
        )}
        {query.data && (
          <>
            {!query.data.items.length && (
              <EmptyState title="暂无股票收益" message="本次回测没有成交记录。" />
            )}
            {!!query.data.items.length && (
              <Table className="min-w-[700px]" aria-label="股票收益明细">
                <TableHeader>
                  <TableRow>
                    <TableHead>股票代码</TableHead>
                    <TableHead>期末状态</TableHead>
                    <TableHead className="text-right">期末股数</TableHead>
                    <TableHead className="text-right">已实现收益（元）</TableHead>
                    <TableHead className="text-right">浮动收益（元）</TableHead>
                    <TableHead className="text-right">总收益（元）</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data.items.map((row) => (
                    <TableRow key={row.symbol}>
                      <TableCell>{row.symbol}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">
                          {Number(row.quantity) ? "持仓中" : "已清仓"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{row.quantity}</TableCell>
                      {[row.realized_profit, row.unrealized_profit, row.profit].map(
                        (value, index) => (
                          <TableCell
                            key={index}
                            className={cn(
                              "text-right tabular-nums",
                              profitTone(value) === "up" && "text-market-up",
                              profitTone(value) === "down" && "text-market-down",
                            )}
                          >
                            {value === null ? "缺少期末估值" : formatMoney(value)}
                          </TableCell>
                        ),
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            <ListPagination
              label="股票收益分页"
              page={page}
              pageSize={query.data.page_size}
              total={query.data.total}
              busy={query.isFetching}
              onChange={setPage}
            />
          </>
        )}
      </CardContent>
    </Card>
  )
}
