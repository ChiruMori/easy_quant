import Decimal from "decimal.js"
import { ArrowUpRight } from "lucide-react"
import { Pause, Play, RefreshCw, Square } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { Link } from "react-router-dom"

import { EmptyState } from "@/components/app-shell"
import { CollapsedDescription } from "@/components/collapsed-description"
import { ConfirmAction } from "@/components/confirm-action"
import { IconButton } from "@/components/icon-button"
import { ListPagination } from "@/components/list-pagination"
import { MetricCard } from "@/components/metric-card"
import { PageHeader } from "@/components/page-header"
import { PortfolioChart } from "@/components/portfolio-chart"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { StrategyPreview } from "@/features/strategies/components/strategy-preview"
import { formatMoney, profitTone } from "@/lib/finance"
import { localizedLabel } from "@/lib/labels"

import type { LiveInstance } from "../api"
import {
  actOnRecommendation,
  getLive,
  getLiveDeliveries,
  getLivePortfolio,
  listOperations,
  pauseLive,
  resumeLive,
  terminateLive,
} from "../api"
import { LiveSchedulePanel } from "../components/live-schedule-panel"
import { ManualOperationDialog } from "../components/manual-operation-dialog"
import { RecommendationActions } from "../components/recommendation-actions"

export function LiveDetailPage({
  instance,
  progressive = false,
}: {
  instance: LiveInstance
  progressive?: boolean
}) {
  const [revision, setRevision] = useState(0)
  const [portfolioRevision, setPortfolioRevision] = useState(0)
  const [deliveryRevision, setDeliveryRevision] = useState(0)
  const [portfolioBusy, setPortfolioBusy] = useState(progressive)
  const [portfolioError, setPortfolioError] = useState<string>()
  const [deliveryPage, setDeliveryPage] = useState(1)
  const [deliveries, setDeliveries] = useState({
    items: instance.notification_deliveries ?? [],
    total: instance.notification_deliveries?.length ?? 0,
    page: 1,
    page_size: 20,
  })
  const [deliveryBusy, setDeliveryBusy] = useState(progressive)
  const [deliveryError, setDeliveryError] = useState<string>()
  const [current, setCurrent] = useState(instance)
  const portfolioRequest = useRef<{
    key: string
    result: ReturnType<typeof getLivePortfolio>
  } | null>(null)
  const deliveryRequest = useRef<{
    key: string
    result: ReturnType<typeof getLiveDeliveries>
  } | null>(null)
  const balances = current.balances ?? current.portfolio
  const series = useMemo(
    () => [
      {
        id: `live:${current.id}`,
        name: "累计收益",
        points: (current.portfolio?.curve ?? []).map((point) => ({
          day: new Date(point.at).toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" }),
          amount: point.profit,
          return_rate: point.return_rate,
        })),
      },
    ],
    [current.id, current.portfolio?.curve],
  )
  useEffect(() => {
    if (!progressive) return
    let active = true
    setPortfolioBusy(true)
    setPortfolioError(undefined)
    const key = `${instance.id}:${revision}:${portfolioRevision}:${current.status}`
    if (portfolioRequest.current?.key !== key)
      portfolioRequest.current = { key, result: getLivePortfolio(instance.id) }
    portfolioRequest.current.result
      .then((portfolio) => {
        if (active) setCurrent((previous) => ({ ...previous, portfolio }))
      })
      .catch((error: unknown) => {
        if (active) setPortfolioError(error instanceof Error ? error.message : "估值加载失败")
      })
      .finally(() => {
        if (active) setPortfolioBusy(false)
      })
    return () => {
      active = false
    }
  }, [instance.id, progressive, revision, portfolioRevision, current.status])
  useEffect(() => {
    if (!progressive) return
    let active = true
    setDeliveryBusy(true)
    setDeliveryError(undefined)
    const key = `${instance.id}:${revision}:${deliveryPage}:${deliveryRevision}`
    if (deliveryRequest.current?.key !== key)
      deliveryRequest.current = { key, result: getLiveDeliveries(instance.id, deliveryPage) }
    deliveryRequest.current.result
      .then((result) => {
        if (active) setDeliveries(result)
      })
      .catch((error: unknown) => {
        if (active) setDeliveryError(error instanceof Error ? error.message : "投递记录加载失败")
      })
      .finally(() => {
        if (active) setDeliveryBusy(false)
      })
    return () => {
      active = false
    }
  }, [instance.id, progressive, revision, deliveryPage, deliveryRevision])
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [operations, setOperations] = useState(
    instance.operations ?? {
      items: instance.recommendations ?? [],
      page: 1,
      page_size: 20,
      total: instance.recommendations?.length ?? 0,
    },
  )
  const [search, setSearch] = useState("")
  const [appliedSearch, setAppliedSearch] = useState("")
  const [filters, setFilters] = useState({ status: "", operationType: "" })
  const [appliedFilters, setAppliedFilters] = useState({ status: "", operationType: "" })
  const [pageBusy, setPageBusy] = useState(false)
  const loading = useRef(false)
  async function loadPage(page: number, query = appliedSearch, selected = appliedFilters) {
    if (loading.current) return
    loading.current = true
    setPageBusy(true)
    setError(undefined)
    try {
      setOperations(
        await listOperations(current.id, page, query, selected.status, selected.operationType),
      )
      setAppliedSearch(query)
      setAppliedFilters(selected)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "列表加载失败，请重试")
    } finally {
      loading.current = false
      setPageBusy(false)
    }
  }
  async function refresh() {
    const latest = await getLive(current.id, progressive)
    if (latest) {
      setCurrent((previous) => ({ ...latest, portfolio: latest.portfolio ?? previous.portfolio }))
      setRevision((value) => value + 1)
      if (latest.operations) await loadPage(operations.page)
    }
  }
  const sending = useRef(false)
  const requests = useRef<Record<string, { signature: string; key: string }>>({})

  async function runAction(action: () => Promise<void>) {
    if (sending.current) return
    sending.current = true
    setBusy(true)
    setError(undefined)
    try {
      await action()
    } catch (caught) {
      const latest = await getLive(current.id, progressive).catch(() => undefined)
      if (latest) {
        setCurrent((previous) => ({ ...latest, portfolio: latest.portfolio ?? previous.portfolio }))
        setRevision((value) => value + 1)
        if (latest.operations) await loadPage(operations.page)
      }
      setError(caught instanceof Error ? caught.message : "处理失败，请重试")
      throw caught
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title={`实盘实例 ${current.name ?? current.id}`}
        description={`状态：${localizedLabel(current.status)}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {current.status === "active" && (
              <ConfirmAction
                icon={Pause}
                label="暂停"
                title="确认暂停实盘"
                description="暂停后停止生成新建议，待操作建议的资金和持仓仍锁定，请继续核对实际成交。"
                destructive={false}
                disabled={busy || current.status !== "active"}
                action={() =>
                  runAction(async () => {
                    const result = await pauseLive(current.id)
                    setCurrent((previous) => ({ ...previous, ...result }))
                  })
                }
              />
            )}
            {current.status === "paused" && (
              <ConfirmAction
                icon={Play}
                label="恢复实盘"
                title="确认恢复实盘"
                description="恢复后将按计划继续生成操作建议，资金及持仓以已记录的实际操作为准。"
                destructive={false}
                disabled={busy}
                action={() =>
                  runAction(async () => {
                    const result = await resumeLive(current.id)
                    setCurrent((previous) => ({ ...previous, ...result }))
                  })
                }
              />
            )}
            {current.status !== "terminated" && (
              <ConfirmAction
                icon={Square}
                label="终止"
                title="确认终止实盘"
                description="终止后资金、持仓、账本及收益数据永久冻结，保留终止时指标与曲线，停止每日运行，无法恢复或继续处理建议。请先核对所有实际成交及待操作建议。"
                disabled={busy || current.status === "terminated"}
                action={() =>
                  runAction(async () => {
                    const result = await terminateLive(current.id)
                    setCurrent((previous) => ({
                      ...previous,
                      ...result,
                      portfolio: result.frozen_portfolio,
                    }))
                  })
                }
              />
            )}
            {current.status !== "terminated" && (
              <IconButton
                icon={RefreshCw}
                label="刷新实盘"
                disabled={busy || pageBusy}
                onClick={() => void runAction(refresh).catch(() => undefined)}
              />
            )}
          </div>
        }
      />
      <LiveSchedulePanel instanceId={current.id} status={current.status} />
      {error && (
        <Alert variant="destructive">
          <AlertTitle>操作未完成</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {busy && <p role="status">正在处理，请稍候…</p>}
      {current.status === "terminated" && (
        <Alert>
          <AlertTitle>实盘已终止 · 数据已冻结</AlertTitle>
          <AlertDescription>
            收益指标与曲线保留至终止时点，停止每日运行及后续估值，历史操作只读。
          </AlertDescription>
        </Alert>
      )}
      <>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="当前收益"
            tone={profitTone(current.portfolio?.profit)}
            value={
              current.portfolio && current.portfolio.profit !== null
                ? `${formatMoney(current.portfolio.profit)} 元`
                : portfolioBusy
                  ? "估值加载中…"
                  : "暂不可估值"
            }
          />
          <MetricCard
            label="当前收益率"
            tone={profitTone(current.portfolio?.return_rate)}
            value={
              current.portfolio && current.portfolio.return_rate !== null
                ? `${(Number(current.portfolio.return_rate) * 100).toFixed(2)}%`
                : "—"
            }
          />
          <MetricCard
            label="可用资金"
            value={
              current.balances || current.portfolio
                ? `${formatMoney(balances?.available_cash)} 元`
                : "—"
            }
          />
          <MetricCard
            label="锁定资金"
            value={
              current.balances || current.portfolio
                ? `${formatMoney(balances?.reserved_cash)} 元`
                : "—"
            }
            description="待操作买入建议预留成交额及预计费用"
          />
        </div>
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>实盘收益曲线</CardTitle>
          </CardHeader>
          <CardContent className="flex min-w-0 flex-col gap-4">
            {portfolioBusy && (
              <div role="status" aria-label="正在加载收益曲线">
                {current.portfolio ? (
                  <p>正在更新收益估值…</p>
                ) : (
                  <Skeleton className="h-60 w-full" />
                )}
              </div>
            )}
            {portfolioError && (
              <Alert variant="destructive">
                <AlertDescription>
                  {portfolioError}
                  <Button
                    variant="outline"
                    onClick={() => setPortfolioRevision((value) => value + 1)}
                  >
                    重试估值
                  </Button>
                </AlertDescription>
              </Alert>
            )}
            <p className="text-sm text-muted-foreground">
              {current.portfolio?.valuation_note ?? "等待真实行情估值。"}
            </p>
            {!!current.portfolio?.missing_symbols.length && (
              <p role="status">缺少估值行情：{current.portfolio.missing_symbols.join("、")}</p>
            )}
            {current.portfolio?.curve.some((point) => point.profit !== null) ? (
              <PortfolioChart
                key={current.id}
                kind="live"
                resourceId={current.id}
                amountLabel="累计收益"
                series={series}
              />
            ) : !portfolioBusy && !portfolioError ? (
              <p>暂无可估值的收益曲线</p>
            ) : null}
            <p className="text-sm">
              锁定持仓：
              {Object.entries(balances?.reserved_positions ?? {})
                .map(([symbol, quantity]) => `${symbol} ${quantity} 股`)
                .join("、") || "无"}
            </p>
            <p className="text-sm">
              资金池：{formatMoney(balances?.capital_pool)} 元 · 当前现金：
              {formatMoney(balances?.cash)} 元
            </p>
            {!!Object.keys(balances?.positions ?? {}).length && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>持仓标的</TableHead>
                    <TableHead>总持仓（股）</TableHead>
                    <TableHead>锁定（股）</TableHead>
                    <TableHead>可用（股）</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(balances?.positions ?? {}).map(([symbol, quantity]) => {
                    const locked = balances?.reserved_positions[symbol] ?? "0"
                    return (
                      <TableRow key={symbol}>
                        <TableCell>{symbol}</TableCell>
                        <TableCell>{quantity}</TableCell>
                        <TableCell>{locked}</TableCell>
                        <TableCell>
                          {Decimal.max(0, new Decimal(quantity).minus(locked)).toFixed()}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </>
      <Card className="min-w-0">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>操作列表</CardTitle>
          {current.status !== "terminated" && (
            <ManualOperationDialog instanceId={current.id} disabled={busy} onSaved={refresh} />
          )}
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-4">
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              void loadPage(1, search, filters)
            }}
          >
            <Input
              aria-label="搜索操作"
              className="min-w-0 flex-1 basis-40"
              placeholder="标的、日期或说明"
              value={search}
              disabled={pageBusy}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Select
              value={filters.status || "all"}
              disabled={pageBusy}
              onValueChange={(value) => {
                const next = { ...filters, status: value === "all" ? "" : value }
                setFilters(next)
                void loadPage(1, appliedSearch, next)
              }}
            >
              <SelectTrigger aria-label="操作状态" className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">全部状态</SelectItem>
                  <SelectItem value="pending">待操作</SelectItem>
                  <SelectItem value="executed">已操作</SelectItem>
                  <SelectItem value="rejected">已拒绝</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <Select
              value={filters.operationType || "all"}
              disabled={pageBusy}
              onValueChange={(value) => {
                const next = { ...filters, operationType: value === "all" ? "" : value }
                setFilters(next)
                void loadPage(1, appliedSearch, next)
              }}
            >
              <SelectTrigger aria-label="操作类型" className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">全部类型</SelectItem>
                  <SelectItem value="buy_signal">买入信号</SelectItem>
                  <SelectItem value="sell_signal">卖出信号</SelectItem>
                  <SelectItem value="manual_buy">手动买入</SelectItem>
                  <SelectItem value="manual_sell">手动卖出</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <Button type="submit" disabled={pageBusy}>
              搜索
            </Button>
          </form>
          {pageBusy && <p role="status">正在加载操作列表…</p>}
          {!operations.items.length && (
            <EmptyState title="暂无操作" message="当前条件下没有操作记录。" />
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>建议/录入日期</TableHead>
                <TableHead>标的</TableHead>
                <TableHead>操作类型</TableHead>
                <TableHead>推荐/录入价格</TableHead>
                <TableHead>股数</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>说明</TableHead>
                <TableHead>实际成交</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {operations.items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>
                    {item.decision_at
                      ? new Date(item.decision_at).toLocaleString("zh-CN", {
                          timeZone: "Asia/Shanghai",
                        })
                      : "历史记录"}
                  </TableCell>
                  <TableCell>{item.instrument_id}</TableCell>
                  <TableCell>
                    {
                      {
                        buy_signal: "买入信号",
                        sell_signal: "卖出信号",
                        manual_buy: "手动买入",
                        manual_sell: "手动卖出",
                      }[
                        item.operation_type ??
                          (item.action === "buy" ? "buy_signal" : "sell_signal")
                      ]
                    }
                  </TableCell>
                  <TableCell>{item.suggested_price || "—"}</TableCell>
                  <TableCell>{item.quantity}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {item.status === "pending"
                        ? "待操作"
                        : item.status === "rejected"
                          ? "已拒绝"
                          : "已操作"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <CollapsedDescription
                      text={
                        item.reason +
                        (item.ratio
                          ? `\n建议按${item.action === "buy" ? "该标的子仓位预算" : "该股持仓"}的 ${new Decimal(item.ratio).mul(100).toFixed()}% 操作（基数 ${formatMoney(item.ratio_basis)}）。`
                          : "")
                      }
                    />
                  </TableCell>
                  <TableCell>
                    {item.actual_quantity
                      ? `${item.actual_quantity} 股 · 价格 ${formatMoney(item.actual_price)} · 费用 ${formatMoney(item.actual_fee)}`
                      : "—"}
                  </TableCell>
                  <TableCell>
                    <div className="flex min-w-32 gap-2">
                      {current.status !== "terminated" &&
                        item.status === "pending" &&
                        !item.operation_type?.startsWith("manual_") && (
                          <RecommendationActions
                            recommendation={item}
                            disabled={busy || item.status !== "pending"}
                            onSubmit={(kind, values = {}) =>
                              runAction(async () => {
                                const signature = JSON.stringify([kind, item.version, values])
                                if (requests.current[item.id]?.signature !== signature)
                                  requests.current[item.id] = {
                                    signature,
                                    key: crypto.randomUUID(),
                                  }
                                const result = await actOnRecommendation(
                                  item.id,
                                  kind,
                                  item.version,
                                  values,
                                  requests.current[item.id].key,
                                )
                                setOperations((previous) => ({
                                  ...previous,
                                  items: previous.items.map((row) =>
                                    row.id === item.id
                                      ? {
                                          ...row,
                                          status: result.recommendation_status,
                                          version: result.version,
                                        }
                                      : row,
                                  ),
                                }))
                                await refresh()
                              })
                            }
                          />
                        )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <ListPagination
            label="实盘操作分页"
            page={operations.page}
            total={operations.total}
            pageSize={operations.page_size}
            busy={pageBusy}
            onChange={(page) => void loadPage(page)}
          />
        </CardContent>
      </Card>
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>通知投递诊断</CardTitle>
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            渠道已接收表示通知服务接受请求，不保证终端已收到。每轮信号汇总发送，投递
            记录持久保存并分页展示，可在日志丢失后核查。
          </p>
          <Button variant="outline" size="sm" className="w-fit max-w-full" asChild>
            <Link to="/notifications">
              <ArrowUpRight />
              检查通知渠道及测试连通性
            </Link>
          </Button>
          {deliveryBusy && (
            <div role="status" aria-label="正在加载投递记录">
              <Skeleton className="h-28 w-full" />
            </div>
          )}
          {deliveryError && (
            <Alert variant="destructive">
              <AlertDescription>
                {deliveryError}
                <Button variant="outline" onClick={() => setDeliveryRevision((value) => value + 1)}>
                  重试投递记录
                </Button>
              </AlertDescription>
            </Alert>
          )}
          {!deliveryBusy && !deliveryError && !deliveries.items.length ? (
            <p className="text-sm text-muted-foreground">
              暂无此实例的投递记录，历史终端接收结果无法追溯。
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>渠道</TableHead>
                  <TableHead>投递状态</TableHead>
                  <TableHead>尝试次数</TableHead>
                  <TableHead>最近时间</TableHead>
                  <TableHead>诊断</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {deliveries.items.map((delivery) => (
                  <TableRow key={delivery.id}>
                    <TableCell>
                      {delivery.channel === "none"
                        ? "未选择有效渠道"
                        : localizedLabel(delivery.channel)}
                    </TableCell>
                    <TableCell>
                      {{
                        delivered: "渠道已接收",
                        sending: "发送中",
                        pending: "待投递",
                        retry: "等待重试",
                        failed: "失败",
                        skipped: "未发送",
                      }[delivery.status] ?? delivery.status}
                    </TableCell>
                    <TableCell>{delivery.attempts}</TableCell>
                    <TableCell>
                      {delivery.updated_at || delivery.created_at
                        ? new Date(delivery.updated_at || delivery.created_at!).toLocaleString(
                            "zh-CN",
                            { timeZone: "Asia/Shanghai" },
                          )
                        : "未记录"}
                    </TableCell>
                    <TableCell>
                      {delivery.error ?? "—"}
                      {delivery.error_code && `（${delivery.error_code}）`}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <ListPagination
            label="实盘投递分页"
            page={deliveries.page}
            total={deliveries.total}
            pageSize={deliveries.page_size}
            busy={deliveryBusy}
            onChange={setDeliveryPage}
          />
        </CardContent>
      </Card>
      <Accordion type="single" collapsible>
        <AccordionItem value="configuration">
          <AccordionTrigger>策略与启动配置</AccordionTrigger>
          <AccordionContent>
            <div className="flex min-w-0 flex-col gap-4">
              <StrategyPreview
                strategy={current.strategy}
                versionId={current.strategy_version_id}
              />
              <Card className="min-w-0">
                <CardHeader>
                  <CardTitle>启动配置</CardTitle>
                </CardHeader>
                <CardContent className="flex min-w-0 flex-col gap-2 break-words">
                  <p>初始资金：{formatMoney(current.initial_cash)}</p>
                  <p>
                    通知渠道：
                    {current.notification_channels
                      ?.map((item) => `${item.name}${item.enabled ? "" : "（已停用）"}`)
                      .join("、") || "历史配置"}
                  </p>
                  <Button variant="outline" size="sm" className="w-fit max-w-full" asChild>
                    <Link to={`/backtests/${current.backtest_id}`}>
                      <ArrowUpRight />
                      查看来源回测
                    </Link>
                  </Button>
                  <pre className="overflow-auto">
                    策略参数：{JSON.stringify(current.parameters ?? {}, null, 2)}
                  </pre>
                  <pre className="overflow-auto">
                    初始持仓：{JSON.stringify(current.initial_positions ?? {}, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  )
}
