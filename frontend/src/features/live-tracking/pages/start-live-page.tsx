import { useQuery } from "@tanstack/react-query"
import { ArrowUpRight } from "lucide-react"
import { useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { listSubscriptions } from "@/features/notifications/api"

import { startLive } from "../api"

export function StartLivePage({
  backtestId,
  strategyVersionId,
  parameters = {},
}: {
  backtestId: string
  strategyVersionId: string
  parameters?: Record<string, unknown>
}) {
  const navigate = useNavigate()
  const channels = useQuery({
    queryKey: ["notifications", "subscriptions"],
    queryFn: listSubscriptions,
  })
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const sending = useRef(false)
  return (
    <Card>
      <CardHeader>
        <CardTitle>配置实盘跟踪</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-sm text-muted-foreground">
          资金和参数独立于回测；系统只生成建议，不会自动下单。
        </p>
        <form
          onSubmit={async (event) => {
            event.preventDefault()
            if (sending.current) return
            sending.current = true
            setBusy(true)
            setError("")
            const data = new FormData(event.currentTarget)
            try {
              const parseObject = (key: string) => {
                const value: unknown = JSON.parse(String(data.get(key)))
                if (!value || typeof value !== "object" || Array.isArray(value))
                  throw new Error("参数和持仓必须为 JSON 对象")
                return value as Record<string, unknown>
              }
              const positions = parseObject("positions")
              if (Object.values(positions).some((value) => typeof value !== "string"))
                throw new Error('持仓数量请使用字符串，例如 {"000001":"100"}')
              const selected = data.getAll("subscription_ids").map(String)
              if (!selected.length) throw new Error("请至少选择一个通知渠道")
              const live = await startLive(backtestId, strategyVersionId, {
                name: String(data.get("name")),
                initial_cash: String(data.get("initial_cash")),
                parameters: parseObject("parameters"),
                positions: positions as Record<string, string>,
                subscription_ids: selected,
                after_market_enabled: data.has("after_market_enabled"),
              })
              navigate(`/live/${live.id}`)
            } catch (caught) {
              setError(caught instanceof Error ? caught.message : "启动失败")
            } finally {
              sending.current = false
              setBusy(false)
            }
          }}
        >
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="live-name">实盘名称</FieldLabel>
              <Input id="live-name" name="name" required maxLength={160} />
            </Field>
            <Field>
              <FieldLabel htmlFor="live-cash">实盘初始资金</FieldLabel>
              <Input
                id="live-cash"
                name="initial_cash"
                type="number"
                min="0.01"
                step="0.01"
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="live-parameters">实盘策略参数（JSON）</FieldLabel>
              <Textarea
                id="live-parameters"
                name="parameters"
                defaultValue={JSON.stringify(parameters, null, 2)}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="live-positions">初始持仓（JSON，数量使用字符串）</FieldLabel>
              <Textarea id="live-positions" name="positions" defaultValue="{}" required />
              <FieldDescription>
                初始资金为可用现金；已有持仓成本暂按 0 记录，不计入初始现金。
              </FieldDescription>
            </Field>
            <FieldSet>
              <FieldLegend>通知渠道（至少选择一个）</FieldLegend>
              {channels.isLoading && <p>正在加载渠道…</p>}
              {channels.error && <p role="alert">{channels.error.message}</p>}
              {channels.data
                ?.filter((item) => item.enabled)
                .map((item) => (
                  <Field key={item.id} orientation="horizontal">
                    <input
                      type="checkbox"
                      id={`channel-${item.id}`}
                      name="subscription_ids"
                      value={item.id}
                    />
                    <FieldLabel htmlFor={`channel-${item.id}`}>
                      {item.name ?? item.channel}
                    </FieldLabel>
                  </Field>
                ))}
              <Button variant="outline" size="sm" className="w-fit max-w-full" asChild>
                <Link to="/notifications">
                  <ArrowUpRight />
                  配置和测试通知渠道
                </Link>
              </Button>
            </FieldSet>
            <Field orientation="horizontal">
              <input id="live-reminder" type="checkbox" name="after_market_enabled" />
              <FieldLabel htmlFor="live-reminder">启用盘后持仓核对提醒</FieldLabel>
            </Field>
            {error && <p role="alert">{error}</p>}
            <Button type="submit" disabled={busy || channels.isLoading || !!channels.error}>
              {busy ? "正在启动…" : "确认启动实盘"}
            </Button>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  )
}
