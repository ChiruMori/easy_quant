import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
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

import { startAcquisition, updateDatasetSources, useDatasets, useMarketDataCoverage } from "../api"
import { SourceToggleForm } from "../components/source-toggle-form"

export function DatasetsPage() {
  const query = useDatasets()
  const coverage = useMarketDataCoverage()
  const queryClient = useQueryClient()
  const [syncingSymbol, setSyncingSymbol] = useState("")
  if (query.isLoading) return <LoadingState label="正在加载数据集" />
  if (query.error) return <ErrorState title="无法加载数据集" message={query.error.message} />
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">数据集与来源</h1>
          <p className="text-muted-foreground">
            查看平台数据覆盖并创建同步任务。系统自动选择可用数据来源。
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/admin/data/import">上传 CSV</Link>
          </Button>
          <Button asChild>
            <Link to="/admin/data/acquisitions">运行拉取</Link>
          </Button>
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {query.data?.map((dataset) => (
          <Card key={dataset.key}>
            <CardHeader>
              <CardTitle>{dataset.name}</CardTitle>
              <CardDescription>{dataset.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                已配置 {dataset.sources.filter((source) => source.enabled).length}{" "}
                个可用来源；失败时自动切换，全部失败后才报告。
              </p>
              <div className="mt-4">
                <SourceToggleForm
                  sources={dataset.sources}
                  onSave={async (sources) => {
                    await updateDatasetSources(
                      dataset.key,
                      sources.map((source) => source.key),
                      sources.filter((source) => source.enabled).map((source) => source.key),
                    )
                    await queryClient.invalidateQueries({ queryKey: ["admin", "datasets"] })
                  }}
                />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>股票数据覆盖</CardTitle>
          <CardDescription>
            当前已维护 {coverage.data?.instrument_count ?? 0}{" "}
            只沪深京股票。十年以上为完全同步，三年以上为部分同步。
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {coverage.isLoading ? (
            <p>正在统计数据覆盖…</p>
          ) : coverage.error ? (
            <p className="text-destructive">无法加载数据覆盖：{coverage.error.message}</p>
          ) : coverage.data?.items.length ? (
            <Table className="min-w-[760px]">
              <TableHeader>
                <TableRow>
                  <TableHead>股票</TableHead>
                  <TableHead>交易所</TableHead>
                  <TableHead>最早日期</TableHead>
                  <TableHead>最新日期</TableHead>
                  <TableHead className="text-right">记录数</TableHead>
                  <TableHead>状态</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {coverage.data.items.map((item) => (
                  <TableRow key={item.symbol}>
                    <TableCell className="max-w-48 truncate font-medium" title={item.name}>
                      {item.symbol} {item.name}
                    </TableCell>
                    <TableCell>{item.exchange}</TableCell>
                    <TableCell>{item.first_trading_day ?? "—"}</TableCell>
                    <TableCell>{item.last_trading_day ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {item.record_count.toLocaleString("zh-CN")}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-2 whitespace-nowrap">
                        <Badge variant="secondary">{item.sync_status}</Badge>
                        {item.updated && <Badge>已更新</Badge>}
                        {item.stale && <Badge variant="destructive">已过时</Badge>}
                        {item.stale && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={syncingSymbol === item.symbol}
                            onClick={async () => {
                              setSyncingSymbol(item.symbol)
                              try {
                                await startAcquisition("daily-bars", true, {
                                  symbols: [item.symbol],
                                  start_day: item.last_trading_day ?? item.previous_trading_day,
                                  end_day: item.previous_trading_day,
                                })
                                await queryClient.invalidateQueries({
                                  queryKey: ["admin", "market-data", "coverage"],
                                })
                              } finally {
                                setSyncingSymbol("")
                              }
                            }}
                          >
                            {syncingSymbol === item.symbol
                              ? "正在创建任务…"
                              : `更新至 ${item.previous_trading_day}`}
                          </Button>
                        )}
                        {item.stale && item.recommended_end_day !== item.previous_trading_day && (
                          <Button
                            size="sm"
                            disabled={syncingSymbol === item.symbol}
                            onClick={async () => {
                              setSyncingSymbol(item.symbol)
                              try {
                                await startAcquisition("daily-bars", true, {
                                  symbols: [item.symbol],
                                  start_day: item.last_trading_day ?? item.previous_trading_day,
                                  end_day: item.recommended_end_day,
                                })
                                await queryClient.invalidateQueries({
                                  queryKey: ["admin", "market-data", "coverage"],
                                })
                              } finally {
                                setSyncingSymbol("")
                              }
                            }}
                          >
                            更新至今日
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-muted-foreground">尚无股票数据，请先上传 CSV 或创建同步任务。</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
