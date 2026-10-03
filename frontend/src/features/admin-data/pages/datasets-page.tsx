import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
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

import { startAcquisition, updateDatasetSources, useDatasets, useMarketDataCoverage } from "../api"
import { SourceToggleForm } from "../components/source-toggle-form"

export function DatasetsPage() {
  const query = useDatasets()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageInput, setPageInput] = useState("1")
  const [cursor, setCursor] = useState<{ after?: string; before?: string }>({})
  const [searchInput, setSearchInput] = useState("")
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("all")
  const [syncingSymbol, setSyncingSymbol] = useState("")
  const coverage = useMarketDataCoverage({
    page,
    search,
    status: status === "all" ? undefined : status,
    ...cursor,
  })
  if (query.isLoading) return <LoadingState label="正在加载数据集" />
  if (query.error) return <ErrorState title="无法加载数据集" message={query.error.message} />

  async function enqueueSync(symbol: string, endDay: string, startDay: string) {
    setSyncingSymbol(symbol)
    try {
      const task = await startAcquisition("daily-bars", true, {
        symbols: [symbol],
        start_day: startDay,
        end_day: endDay,
      })
      toast.success(`同步任务 ${task.id} 已进入队列`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "无法创建同步任务")
    } finally {
      setSyncingSymbol("")
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">数据集与来源</h1>
          <p className="text-muted-foreground">查看平台数据覆盖并创建同步任务。</p>
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
            <CardContent className="flex flex-col gap-4">
              <p className="text-sm text-muted-foreground">
                已配置 {dataset.sources.filter((source) => source.enabled).length}{" "}
                个可用来源；失败时自动切换。
              </p>
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
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>股票数据覆盖</CardTitle>
          <CardDescription>
            当前已维护 {coverage.data?.instrument_count ?? 0} 只沪深京股票；列表按服务端分页加载。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(event) => {
              event.preventDefault()
              setPage(1)
              setPageInput("1")
              setCursor({})
              setSearch(searchInput.trim())
            }}
          >
            <div className="min-w-64 flex-1">
              <label className="text-sm font-medium" htmlFor="instrument-search">
                名称或代码
              </label>
              <Input
                id="instrument-search"
                placeholder="例如 平安银行 或 000001"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
              />
            </div>
            <div className="w-44">
              <label className="text-sm font-medium" htmlFor="coverage-status">
                同步状态
              </label>
              <Select
                value={status}
                onValueChange={(value) => {
                  setStatus(value)
                  setPage(1)
                  setPageInput("1")
                  setCursor({})
                }}
              >
                <SelectTrigger className="w-full" id="coverage-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="all">全部状态</SelectItem>
                    <SelectItem value="完全同步">完全同步</SelectItem>
                    <SelectItem value="部分同步">部分同步</SelectItem>
                    <SelectItem value="数据不足">数据不足</SelectItem>
                    <SelectItem value="未同步">未同步</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <Button type="submit">搜索</Button>
          </form>
        </CardContent>
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
                      <Link
                        className="underline-offset-4 hover:underline"
                        to={`/admin/data/instruments/${item.symbol}`}
                      >
                        {item.symbol} {item.name}
                      </Link>
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
                            onClick={() =>
                              void enqueueSync(
                                item.symbol,
                                item.previous_trading_day,
                                item.last_trading_day ?? item.previous_trading_day,
                              )
                            }
                          >
                            更新至 {item.previous_trading_day}
                          </Button>
                        )}
                        {item.stale && item.recommended_end_day !== item.previous_trading_day && (
                          <Button
                            size="sm"
                            disabled={syncingSymbol === item.symbol}
                            onClick={() =>
                              void enqueueSync(
                                item.symbol,
                                item.recommended_end_day,
                                item.last_trading_day ?? item.previous_trading_day,
                              )
                            }
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
            <p className="text-muted-foreground">没有符合条件的股票。</p>
          )}
        </CardContent>
        {coverage.data && coverage.data.total > 0 && (
          <CardContent className="flex flex-wrap items-end justify-between gap-3 border-t pt-4">
            <p className="text-sm text-muted-foreground">
              第 {coverage.data.page} /{" "}
              {Math.max(1, Math.ceil(coverage.data.total / coverage.data.page_size))} 页，共{" "}
              {coverage.data.total.toLocaleString("zh-CN")} 条
            </p>
            <div className="flex flex-wrap items-end gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page <= 1 || coverage.isFetching}
                onClick={() => {
                  setCursor({ before: coverage.data.previous_cursor ?? undefined })
                  setPage((value) => value - 1)
                  setPageInput(String(page - 1))
                }}
              >
                上一页
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={
                  page * coverage.data.page_size >= coverage.data.total || coverage.isFetching
                }
                onClick={() => {
                  setCursor({ after: coverage.data.next_cursor ?? undefined })
                  setPage((value) => value + 1)
                  setPageInput(String(page + 1))
                }}
              >
                下一页
              </Button>
              <form
                className="flex items-end gap-2"
                onSubmit={(event) => {
                  event.preventDefault()
                  const target = Number(pageInput)
                  const lastPage = Math.ceil(coverage.data.total / coverage.data.page_size)
                  if (!Number.isSafeInteger(target) || target < 1 || target > lastPage) {
                    toast.error(`请输入 1 到 ${lastPage} 之间的页码`)
                    return
                  }
                  setCursor({})
                  setPage(target)
                }}
              >
                <FieldGroup className="w-auto">
                  <Field className="w-24 gap-1">
                    <FieldLabel htmlFor="coverage-page">页码</FieldLabel>
                    <Input
                      id="coverage-page"
                      type="number"
                      min={1}
                      max={Math.ceil(coverage.data.total / coverage.data.page_size)}
                      value={pageInput}
                      onChange={(event) => setPageInput(event.target.value)}
                    />
                  </Field>
                </FieldGroup>
                <Button size="sm" type="submit" disabled={coverage.isFetching}>
                  跳转
                </Button>
              </form>
            </div>
          </CardContent>
        )}
      </Card>
    </div>
  )
}
