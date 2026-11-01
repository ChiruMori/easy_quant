import { useQuery, useQueryClient } from "@tanstack/react-query"
import { CalendarClock, ChevronDown, Database, FileUp, RefreshCw } from "lucide-react"
import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { ConfirmAction } from "@/components/confirm-action"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { localizedLabel } from "@/lib/labels"

import {
  getAcquisition,
  startAcquisition,
  updateDatasetSources,
  useDatasets,
  useMarketDataCoverage,
} from "../api"
import { SourceToggleForm } from "../components/source-toggle-form"
import type { Acquisition } from "../types"
import { IndicesPanel } from "./indices-page"

export function DatasetsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get("tab") === "indices" ? "indices" : "stocks"
  const query = useDatasets()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageInput, setPageInput] = useState("1")
  const [pageError, setPageError] = useState("")
  const [cursor, setCursor] = useState<{ after?: string; before?: string }>({})
  const [searchInput, setSearchInput] = useState("")
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("all")
  const [syncingSymbol, setSyncingSymbol] = useState("")
  const [syncTask, setSyncTask] = useState<Acquisition | null>(null)
  const [confirmRefresh, setConfirmRefresh] = useState(false)
  const [syncError, setSyncError] = useState("")
  const [handledTaskId, setHandledTaskId] = useState("")
  const syncQuery = useQuery({
    queryKey: ["admin", "market-data", "acquisition", syncTask?.id],
    queryFn: () => getAcquisition(syncTask!.id),
    enabled: Boolean(syncTask?.id),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "queued") ? 1000 : false,
  })
  const currentSyncTask = syncQuery.data ?? syncTask
  const coverage = useMarketDataCoverage({
    instrument_type: "stock",
    page,
    search,
    status: status === "all" ? undefined : status,
    ...cursor,
  })
  useEffect(() => {
    if (
      currentSyncTask?.id &&
      currentSyncTask.id !== handledTaskId &&
      ["succeeded", "failed"].includes(currentSyncTask.status)
    ) {
      setHandledTaskId(currentSyncTask.id)
      void queryClient.invalidateQueries({ queryKey: ["admin", "market-data", "coverage"] })
    }
  }, [currentSyncTask, handledTaskId, queryClient])
  if (query.isLoading) return <LoadingState label="正在加载数据集" />
  if (query.error) return <ErrorState title="无法加载数据集" message={query.error.message} />

  async function enqueueSync(symbol: string, endDay: string, startDay: string) {
    setSyncingSymbol(symbol)
    setSyncError("")
    setSyncTask(null)
    try {
      const task = await startAcquisition("daily-bars", true, {
        symbols: [symbol],
        start_day: startDay,
        end_day: endDay,
      })
      setSyncTask(task)
    } catch (error) {
      setSyncError(error instanceof Error ? error.message : "无法创建同步任务")
    } finally {
      setSyncingSymbol("")
    }
  }

  async function refreshSuspensions() {
    if (!coverage.data?.recommended_end_day) return
    setSyncingSymbol("停复牌状态")
    setSyncError("")
    setSyncTask(null)
    try {
      setSyncTask(
        await startAcquisition("trading-status", true, {
          end_day: coverage.data.recommended_end_day,
        }),
      )
    } catch (error) {
      setSyncError(error instanceof Error ? error.message : "无法创建停复牌状态任务")
      throw error
    } finally {
      setSyncingSymbol("")
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <ConfirmAction
        open={confirmRefresh}
        onOpenChange={setConfirmRefresh}
        label="刷新停复牌状态"
        title="刷新停复牌状态？"
        description="将创建后台任务，更新股票停复牌状态。确认后开始刷新。"
        destructive={false}
        action={refreshSuspensions}
      />
      <PageHeader
        title="数据管理"
        description="维护股票与指数行情，查看覆盖并配置可用来源。"
        actions={
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button>
                <Database data-icon="inline-start" />
                数据维护
                <ChevronDown data-icon="inline-end" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuGroup>
                <DropdownMenuItem asChild>
                  <Link to="/admin/data/import">
                    <FileUp />
                    上传数据
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link to="/admin/data/acquisitions">
                    <Database />
                    范围拉取
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem
                  disabled={
                    !coverage.data?.recommended_end_day ||
                    Boolean(syncingSymbol) ||
                    ["queued", "running"].includes(currentSyncTask?.status ?? "")
                  }
                  onSelect={() => setConfirmRefresh(true)}
                >
                  <RefreshCw />
                  刷新停复牌状态
                </DropdownMenuItem>
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuItem asChild>
                  <Link to="/admin/schedules">
                    <CalendarClock />
                    定时与整体维护
                  </Link>
                </DropdownMenuItem>
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        }
      />
      <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <section aria-label="标的数据" className="min-w-0">
          <Tabs
            value={tab}
            onValueChange={(value) => {
              const next = new URLSearchParams(searchParams)
              if (value === "indices") next.set("tab", "indices")
              else next.delete("tab")
              setSearchParams(next, { replace: true })
            }}
          >
            <TabsList aria-label="标的类型">
              <TabsTrigger value="stocks">股票</TabsTrigger>
              <TabsTrigger value="indices">指数</TabsTrigger>
            </TabsList>
            <TabsContent value="stocks">
              <Card>
                <CardHeader>
                  <CardTitle>股票数据覆盖</CardTitle>
                  <CardDescription>
                    当前已维护 {coverage.data?.instrument_count ?? 0}
                    只股票；补齐日线时沿用已有复权口径。
                    {coverage.data?.recommended_end_day &&
                      ` 当前应更新至 ${coverage.data.recommended_end_day}（Asia/Shanghai，按日线发布时刻计算）。`}
                    {coverage.data?.calendar_estimated &&
                      " 本地交易日历未覆盖目标日期，当前按工作日估算，请通过整体同步刷新日历后核实。"}
                    完全同步还要求历史跨度达到十年，不代表期间没有缺失。
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {syncingSymbol && <p aria-live="polite">正在为 {syncingSymbol} 创建同步任务…</p>}
                  {syncError && <p role="alert">创建同步任务失败：{syncError}</p>}
                  {currentSyncTask && (
                    <div className="mb-4 flex flex-col gap-2 text-sm" aria-live="polite">
                      <p role={currentSyncTask.status === "failed" ? "alert" : undefined}>
                        {currentSyncTask.dataset_key === "trading-status"
                          ? "停复牌状态"
                          : `股票 ${currentSyncTask.symbols?.join("、") ?? ""}`}{" "}
                        同步任务：
                        {localizedLabel(currentSyncTask.status)}
                        {currentSyncTask.status === "succeeded" &&
                          `，取得 ${currentSyncTask.record_count ?? 0} 条${currentSyncTask.dataset_key === "trading-status" ? "状态记录" : " K 线"}${currentSyncTask.new_record_count === undefined ? "" : `，新增 ${currentSyncTask.new_record_count} 条`}`}
                        {currentSyncTask.message && `；${currentSyncTask.message}`}
                      </p>
                      {currentSyncTask.status === "failed" && currentSyncTask.attempts?.length ? (
                        <details>
                          <summary>查看来源失败原因</summary>
                          {currentSyncTask.attempts.map((attempt, index) => (
                            <p className="break-words" key={`${attempt.source_key}-${index}`}>
                              {attempt.source_key} 第 {attempt.attempt} 次：{attempt.message}
                            </p>
                          ))}
                        </details>
                      ) : null}
                    </div>
                  )}
                  {syncQuery.error && (
                    <p role="alert">任务状态刷新失败：{syncQuery.error.message}</p>
                  )}
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
                    <div className="min-w-0 flex-1 basis-48">
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
                            <SelectItem value="数据落后">数据落后</SelectItem>
                            <SelectItem value="部分同步">部分同步</SelectItem>
                            <SelectItem value="数据不足">数据不足</SelectItem>
                            <SelectItem value="未同步">未同步</SelectItem>
                            <SelectItem value="已停牌">已停牌</SelectItem>
                            <SelectItem value="已退市">已退市</SelectItem>
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
                                <Badge
                                  variant={
                                    item.status === "active" && item.sync_status === "数据落后"
                                      ? "destructive"
                                      : "secondary"
                                  }
                                >
                                  {item.status === "suspended"
                                    ? "已停牌"
                                    : item.status === "delisted"
                                      ? "已退市"
                                      : item.sync_status}
                                </Badge>
                                {item.status === "active" && item.updated && <Badge>已更新</Badge>}
                                {item.status === "active" && item.publication_pending && (
                                  <Badge variant="outline">来源尚未发布新数据</Badge>
                                )}
                                {item.status === "active" &&
                                  item.stale &&
                                  item.sync_status !== "数据落后" && (
                                    <Badge variant="destructive">已过时</Badge>
                                  )}
                                {item.status === "active" && item.stale && (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    disabled={
                                      Boolean(syncingSymbol) ||
                                      ["queued", "running"].includes(currentSyncTask?.status ?? "")
                                    }
                                    onClick={() =>
                                      void enqueueSync(
                                        item.symbol,
                                        item.recommended_end_day,
                                        item.last_trading_day ?? item.recommended_end_day,
                                      )
                                    }
                                  >
                                    更新至 {item.recommended_end_day}
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
                  <CardContent className="flex flex-col gap-3 border-t pt-4 lg:flex-row lg:items-center lg:justify-between">
                    <p className="text-sm text-muted-foreground">
                      第 {coverage.data.page} /{" "}
                      {Math.max(1, Math.ceil(coverage.data.total / coverage.data.page_size))} 页，共{" "}
                      {coverage.data.total.toLocaleString("zh-CN")} 条
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
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
                        variant="outline"
                        disabled={
                          page * coverage.data.page_size >= coverage.data.total ||
                          coverage.isFetching
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
                        className="flex flex-wrap items-center gap-2"
                        onSubmit={(event) => {
                          event.preventDefault()
                          const target = Number(pageInput)
                          const lastPage = Math.ceil(coverage.data.total / coverage.data.page_size)
                          if (!Number.isSafeInteger(target) || target < 1 || target > lastPage) {
                            setPageError(`请输入 1 到 ${lastPage} 之间的页码`)
                            return
                          }
                          setPageError("")
                          setCursor({})
                          setPage(target)
                        }}
                      >
                        <FieldGroup className="w-24 shrink-0 gap-0">
                          <Field className="gap-0">
                            <FieldLabel className="sr-only" htmlFor="coverage-page">
                              页码
                            </FieldLabel>
                            <Input
                              id="coverage-page"
                              type="text"
                              inputMode="numeric"
                              pattern="[0-9]*"
                              aria-label="页码"
                              value={pageInput}
                              onChange={(event) => setPageInput(event.target.value)}
                            />
                          </Field>
                        </FieldGroup>
                        <Button type="submit" disabled={coverage.isFetching}>
                          跳转
                        </Button>
                      </form>
                      {pageError && <p role="alert">{pageError}</p>}
                    </div>
                  </CardContent>
                )}
              </Card>
            </TabsContent>
            <TabsContent value="indices">
              <IndicesPanel />
            </TabsContent>
          </Tabs>
        </section>
        <aside id="sources" aria-label="数据来源" className="flex min-w-0 flex-col gap-3">
          <div>
            <h2 className="text-base font-semibold">数据来源</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              点击即保存 · 高亮为启用 · 失败时切换来源
            </p>
          </div>
          {query.data?.map((dataset) => (
            <Card key={dataset.key} id={`dataset-${dataset.key}`} className="gap-3 py-3">
              <CardHeader className="gap-1 px-4 sm:px-4">
                <CardTitle>{dataset.name}</CardTitle>
                <CardDescription className="text-xs">{dataset.description}</CardDescription>
              </CardHeader>
              <CardContent className="px-4 sm:px-4">
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
        </aside>
      </div>
    </div>
  )
}
