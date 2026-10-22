import Decimal from "decimal.js"
import { useRef, useState } from "react"
import { Link } from "react-router-dom"
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { EmptyState } from "@/components/app-shell"
import { ConfirmAction } from "@/components/confirm-action"
import { MetricCard } from "@/components/metric-card"
import { PageHeader } from "@/components/page-header"
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { StrategyPreview } from "@/features/strategies/components/strategy-preview"
import { localizedLabel } from "@/lib/labels"

import type { LiveInstance } from "../api"
import { actOnRecommendation, getLive, listOperations, pauseLive, terminateLive } from "../api"
import { ManualOperationDialog } from "../components/manual-operation-dialog"
import { RecommendationActions } from "../components/recommendation-actions"

export function LiveDetailPage({ instance }: { instance: LiveInstance }) {
  const [current, setCurrent] = useState(instance)
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
  const [pageBusy, setPageBusy] = useState(false)
  const loading = useRef(false)
  async function loadPage(page: number, query = appliedSearch) {
    if (loading.current) return
    loading.current = true
    setPageBusy(true)
    setError(undefined)
    try {
      setOperations(await listOperations(current.id, page, query))
      setAppliedSearch(query)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "列表加载失败，请重试")
    } finally {
      loading.current = false
      setPageBusy(false)
    }
  }
  async function refresh() {
    const latest = await getLive(current.id)
    if (latest) {
      setCurrent(latest)
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
      const latest = await getLive(current.id).catch(() => undefined)
      if (latest) {
        setCurrent(latest)
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
      />
      {error && (
        <Alert variant="destructive">
          <AlertTitle>操作未完成</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {busy && <p role="status">正在处理，请稍候…</p>}
      <div className="flex flex-wrap gap-2">
        <ConfirmAction
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
        <ConfirmAction
          label="终止"
          title="确认终止实盘"
          description="终止后停止实盘分析，已有建议及实际操作保留，请核对未处理成交。"
          disabled={busy || current.status === "terminated"}
          action={() =>
            runAction(async () => {
              const result = await terminateLive(current.id)
              setCurrent((previous) => ({ ...previous, ...result }))
            })
          }
        />
        <ManualOperationDialog
          instanceId={current.id}
          disabled={busy || current.status === "terminated"}
          onSaved={refresh}
        />
        <Button
          variant="outline"
          disabled={busy || pageBusy}
          onClick={() => void runAction(refresh).catch(() => undefined)}
        >
          刷新实盘
        </Button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="当前收益"
          value={
            current.portfolio && current.portfolio.profit !== null
              ? `${Number(current.portfolio.profit).toFixed(2)} 元`
              : "暂不可估值"
          }
        />
        <MetricCard
          label="当前收益率"
          value={
            current.portfolio && current.portfolio.return_rate !== null
              ? `${(Number(current.portfolio.return_rate) * 100).toFixed(2)}%`
              : "—"
          }
        />
        <MetricCard
          label="可用资金"
          value={current.portfolio ? `${current.portfolio.available_cash} 元` : "—"}
        />
        <MetricCard
          label="锁定资金"
          value={current.portfolio ? `${current.portfolio.reserved_cash} 元` : "—"}
          description="待操作买入建议预留成交额及预计费用"
        />
      </div>
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>实盘收益曲线</CardTitle>
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            {current.portfolio?.valuation_note ?? "等待真实行情估值。"}
          </p>
          {!!current.portfolio?.missing_symbols.length && (
            <p role="status">缺少估值行情：{current.portfolio.missing_symbols.join("、")}</p>
          )}
          {current.portfolio?.curve.some((point) => point.profit !== null) ? (
            <div className="h-64 min-w-0" role="img" aria-label="实盘以来累计收益曲线，单位元">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={current.portfolio.curve.map((point) => ({
                    date: new Date(point.at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }),
                    profit: point.profit === null ? null : Number(point.profit),
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" minTickGap={60} />
                  <YAxis width={65} />
                  <Tooltip formatter={(value: number) => [`${value.toFixed(2)} 元`, "累计收益"]} />
                  <Line
                    dataKey="profit"
                    name="累计收益（元）"
                    type="linear"
                    stroke="var(--primary)"
                    connectNulls={false}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p>暂无可估值的收益曲线</p>
          )}
          <p className="text-sm">
            锁定持仓：
            {Object.entries(current.portfolio?.reserved_positions ?? {})
              .map(([symbol, quantity]) => `${symbol} ${quantity} 股`)
              .join("、") || "无"}
          </p>
          <p className="text-sm">
            资金池：{current.portfolio?.capital_pool ?? "—"} 元 · 当前现金：
            {current.portfolio?.cash ?? "—"} 元
          </p>
          {!!Object.keys(current.portfolio?.positions ?? {}).length && (
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
                {Object.entries(current.portfolio?.positions ?? {}).map(([symbol, quantity]) => {
                  const locked = current.portfolio?.reserved_positions[symbol] ?? "0"
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
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>操作列表</CardTitle>
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-4">
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              void loadPage(1, search)
            }}
          >
            <Input
              aria-label="搜索操作"
              className="min-w-0 flex-1 basis-40"
              placeholder="标的、日期、状态或操作类型"
              value={search}
              disabled={pageBusy}
              onChange={(event) => setSearch(event.target.value)}
            />
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
                <TableHead>说明与处理</TableHead>
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
                    <div className="flex min-w-56 flex-col gap-2">
                      <p className="max-w-sm break-words">
                        {item.reason} · {localizedLabel(item.status)}
                      </p>
                      {item.actual_quantity && (
                        <p className="text-sm text-muted-foreground">
                          实际成交 {item.actual_quantity} 股 · 价格 {item.actual_price} · 费用{" "}
                          {item.actual_fee}
                        </p>
                      )}
                      {item.ratio && (
                        <p className="text-sm text-muted-foreground">
                          建议按{item.action === "buy" ? "该标的子仓位预算" : "该股持仓"}的{" "}
                          {Number(item.ratio) * 100}% 操作（基数 {item.ratio_basis}）。
                        </p>
                      )}
                      {!item.operation_type?.startsWith("manual_") && (
                        <RecommendationActions
                          recommendation={item}
                          disabled={busy || item.status !== "pending"}
                          onSubmit={(kind, values = {}) =>
                            runAction(async () => {
                              const signature = JSON.stringify([kind, item.version, values])
                              if (requests.current[item.id]?.signature !== signature)
                                requests.current[item.id] = { signature, key: crypto.randomUUID() }
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
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              disabled={pageBusy || operations.page <= 1}
              onClick={() => void loadPage(operations.page - 1)}
            >
              上一页
            </Button>
            <p>
              第 {operations.page} /{" "}
              {Math.max(1, Math.ceil(operations.total / operations.page_size))} 页 · 共{" "}
              {operations.total} 条
            </p>
            <Button
              variant="outline"
              disabled={pageBusy || operations.page * operations.page_size >= operations.total}
              onClick={() => void loadPage(operations.page + 1)}
            >
              下一页
            </Button>
          </div>
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
                  <p>初始资金：{current.initial_cash ?? "—"}</p>
                  <p>
                    通知渠道：
                    {current.notification_channels
                      ?.map((item) => `${item.name}${item.enabled ? "" : "（已停用）"}`)
                      .join("、") || "历史配置"}
                  </p>
                  <Link className="underline" to={`/backtests/${current.backtest_id}`}>
                    查看来源回测
                  </Link>
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
