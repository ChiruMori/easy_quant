import { useRef, useState } from "react"
import { Link } from "react-router-dom"

import { PageHeader } from "@/components/page-header"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { StrategyPreview } from "@/features/strategies/components/strategy-preview"
import { localizedLabel } from "@/lib/labels"

import type { LiveInstance } from "../api"
import { actOnRecommendation, getLive, pauseLive, terminateLive } from "../api"
import { RecommendationActions } from "../components/recommendation-actions"

export function LiveDetailPage({ instance }: { instance: LiveInstance }) {
  const [current, setCurrent] = useState(instance)
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
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
      setError(caught instanceof Error ? caught.message : "处理失败，请重试")
      const latest = await getLive(current.id).catch(() => undefined)
      if (latest) setCurrent(latest)
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
      <StrategyPreview strategy={current.strategy} versionId={current.strategy_version_id} />
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
      {error && (
        <Alert variant="destructive">
          <AlertTitle>操作未完成</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {busy && <p role="status">正在处理，请稍候…</p>}
      <div className="flex gap-2">
        <Button
          variant="outline"
          disabled={busy || current.status !== "active"}
          onClick={() =>
            void runAction(async () => {
              const result = await pauseLive(current.id)
              setCurrent((previous) => ({ ...previous, ...result }))
            })
          }
        >
          暂停
        </Button>
        <Button
          variant="destructive"
          disabled={busy || current.status === "terminated"}
          onClick={() =>
            void runAction(async () => {
              const result = await terminateLive(current.id)
              setCurrent((previous) => ({ ...previous, ...result }))
            })
          }
        >
          终止
        </Button>
      </div>
      <h2 className="text-lg font-semibold">建议</h2>
      <div className="flex flex-col gap-4">
        {current.recommendations?.map((item) => (
          <Card key={item.id}>
            <CardHeader>
              <CardTitle>
                {item.instrument_id} · {localizedLabel(item.action)} {item.quantity}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-4 text-sm text-muted-foreground">
                {item.reason} · {localizedLabel(item.status)}
              </p>
              {item.ratio && (
                <p className="mb-4 text-sm">
                  建议按{item.action === "buy" ? "可用现金" : "该股持仓"}的{" "}
                  {Number(item.ratio) * 100}% 操作（基数 {item.ratio_basis}）。请按实际成交回填。
                </p>
              )}
              <RecommendationActions
                disabled={busy || item.status !== "pending"}
                onSubmit={(kind, values = {}) =>
                  void runAction(async () => {
                    const signature = JSON.stringify([kind, item.version, values])
                    if (requests.current[item.id]?.signature !== signature) {
                      requests.current[item.id] = { signature, key: crypto.randomUUID() }
                    }
                    const result = await actOnRecommendation(
                      item.id,
                      kind,
                      item.version,
                      values,
                      requests.current[item.id].key,
                    )
                    setCurrent((previous) => ({
                      ...previous,
                      recommendations: previous.recommendations?.map((row) =>
                        row.id === item.id
                          ? {
                              ...row,
                              status: result.recommendation_status,
                              version: result.version,
                            }
                          : row,
                      ),
                    }))
                  })
                }
              />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
