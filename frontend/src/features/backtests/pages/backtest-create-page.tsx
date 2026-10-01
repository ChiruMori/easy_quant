import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useNavigate } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { listStrategies } from "@/features/strategies/api"
import { ApiError } from "@/lib/api/client"

import { createBacktest } from "../api"

export function BacktestCreatePage() {
  const navigate = useNavigate()
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: listStrategies })
  const [versionId, setVersionId] = useState("")
  const [error, setError] = useState("")
  const [actionUrl, setActionUrl] = useState("")
  if (strategies.isLoading) return <LoadingState label="正在加载策略" />
  if (strategies.error)
    return <ErrorState title="无法加载策略" message={strategies.error.message} />
  const versions =
    strategies.data?.flatMap((strategy) =>
      strategy.versions.map((version) => ({ ...version, strategyName: strategy.name })),
    ) ?? []
  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>创建回测</CardTitle>
        <CardDescription>
          标的由策略通过平台因子选择；回测固定使用所选的不可变策略版本。
        </CardDescription>
      </CardHeader>
      <form
        onSubmit={async (event) => {
          event.preventDefault()
          const form = event.currentTarget
          const data = new FormData(form)
          setError("")
          setActionUrl("")
          try {
            const run = await createBacktest({
              strategy_version_id: versionId,
              start_day: data.get("start"),
              end_day: data.get("end"),
              initial_cash: data.get("cash"),
              fee_rate: data.get("fee"),
              slippage_rate: data.get("slippage"),
              benchmark: data.get("benchmark") || null,
              random_seed: Number(data.get("seed")),
            })
            navigate(`/backtests/${run.id}`)
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : "无法创建回测")
            if (reason instanceof ApiError) {
              setActionUrl(String(reason.details?.action_url ?? ""))
            }
          }
        }}
      >
        <CardContent>
          <FieldGroup>
            <Field>
              <FieldLabel>策略版本</FieldLabel>
              <Select value={versionId} onValueChange={setVersionId}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="选择一个已保存策略版本" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {versions.map((version) => (
                      <SelectItem key={version.id} value={version.id}>
                        {version.strategyName} · v{version.number}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <FieldDescription>策略本身负责选股，回测表单不重复配置标的。</FieldDescription>
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="start">开始日期</FieldLabel>
                <Input id="start" type="date" name="start" required />
              </Field>
              <Field>
                <FieldLabel htmlFor="end">结束日期</FieldLabel>
                <Input id="end" type="date" name="end" required />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="cash">初始资金</FieldLabel>
              <Input id="cash" type="number" name="cash" min="1" defaultValue="100000" required />
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="fee">手续费率</FieldLabel>
                <Input
                  id="fee"
                  type="number"
                  name="fee"
                  min="0"
                  step="0.0001"
                  defaultValue="0.0003"
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="slippage">滑点率</FieldLabel>
                <Input
                  id="slippage"
                  type="number"
                  name="slippage"
                  min="0"
                  step="0.0001"
                  defaultValue="0.0001"
                />
              </Field>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="benchmark">基准</FieldLabel>
                <Input id="benchmark" name="benchmark" placeholder="例如 000300" />
              </Field>
              <Field>
                <FieldLabel htmlFor="seed">随机种子</FieldLabel>
                <Input id="seed" type="number" name="seed" defaultValue="0" />
              </Field>
            </div>
            {error && (
              <Alert variant="destructive">
                <AlertTitle>回测创建失败</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
                {actionUrl && (
                  <Button
                    className="mt-3"
                    variant="outline"
                    type="button"
                    onClick={() => navigate(actionUrl)}
                  >
                    前往数据管理同步
                  </Button>
                )}
              </Alert>
            )}
          </FieldGroup>
        </CardContent>
        <CardFooter>
          <Button type="submit" disabled={!versionId}>
            开始回测
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
