import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { localizedLabel } from "@/lib/labels"

import {
  addStrategyVersion,
  createStrategy,
  listStrategies,
  listStrategyRuns,
  listStrategyTemplates,
  runStrategy,
} from "../api"
import { StrategyEditor } from "../components/strategy-editor"
import type { StrategyRun } from "../types"

const FALLBACK = `def before_market(context, parameters):
    return []


def on_market(context, parameters):
    return []


def after_market(context, parameters):
    return []
`
const loadDraft = () => {
  try {
    return JSON.parse(localStorage.getItem("strategy-draft") ?? "{}") as {
      name?: string
      description?: string
      source?: string
    }
  } catch {
    return {}
  }
}

export function StrategiesPage() {
  const queryClient = useQueryClient()
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: listStrategies })
  const templates = useQuery({ queryKey: ["strategy-templates"], queryFn: listStrategyTemplates })
  const draft = loadDraft()
  const [selected, setSelected] = useState("new")
  const [name, setName] = useState(draft.name ?? "")
  const [description, setDescription] = useState(draft.description ?? "")
  const [source, setSource] = useState(draft.source ?? FALLBACK)
  const [result, setResult] = useState<StrategyRun | null>(null)
  const [tab, setTab] = useState("editor")
  const [tradingDay, setTradingDay] = useState("")
  const [message, setMessage] = useState("")
  useEffect(() => {
    localStorage.setItem("strategy-draft", JSON.stringify({ name, description, source }))
  }, [name, description, source])
  const save = useMutation({
    mutationFn: async () => {
      if (selected === "new") {
        const created = await createStrategy({ name, description, source_code: source })
        return created.id
      }
      await addStrategyVersion(selected, source)
      return selected
    },
    onSuccess: async (strategyId) => {
      setSelected(strategyId)
      setMessage("策略版本已保存")
      localStorage.removeItem("strategy-draft")
      await queryClient.invalidateQueries({ queryKey: ["strategies"] })
    },
    onError: (error) => setMessage(error.message),
  })
  const runs = useQuery({
    queryKey: ["strategy-runs", selected],
    queryFn: () => listStrategyRuns(selected),
    enabled: selected !== "new",
    refetchInterval: (query) =>
      query.state.data?.some((item) => ["queued", "running"].includes(item.status)) ? 1000 : false,
  })
  useEffect(() => {
    if (!result) return
    const refreshed = runs.data?.find((item) => item.id === result.id)
    if (refreshed) setResult(refreshed)
  }, [result, runs.data])
  if (strategies.isLoading || templates.isLoading)
    return <LoadingState label="正在加载策略工作台" />
  if (strategies.error || templates.error)
    return (
      <ErrorState
        title="无法加载策略"
        message={(strategies.error ?? templates.error)?.message ?? "未知错误"}
      />
    )
  const visibleRun = result ?? runs.data?.[0] ?? null
  const choose = (value: string) => {
    setSelected(value)
    setResult(null)
    setMessage("")
    if (value === "new") {
      setName("")
      setDescription("")
      setSource(FALLBACK)
      return
    }
    const item = strategies.data?.find((row) => row.id === value)
    if (item) {
      setName(item.name)
      setDescription(item.description)
      setSource(item.versions.at(-1)?.source_code ?? FALLBACK)
    }
  }
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">策略工作台</h1>
        <p className="text-muted-foreground">
          使用平台因子选股并返回交易信号；每次保存都会创建不可变版本。
        </p>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="editor">编辑策略</TabsTrigger>
          <TabsTrigger value="result">最近运行</TabsTrigger>
        </TabsList>
        <TabsContent value="editor">
          <Card>
            <CardHeader>
              <CardTitle>策略定义</CardTitle>
              <CardDescription>草稿自动保存在当前浏览器，已保存版本由平台管理。</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-5">
              <FieldGroup>
                <Field>
                  <FieldLabel>已有策略</FieldLabel>
                  <Select value={selected} onValueChange={choose}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="新建策略" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectItem value="new">新建策略</SelectItem>
                        {strategies.data?.map((item) => (
                          <SelectItem key={item.id} value={item.id}>
                            {item.name} · v{item.versions.at(-1)?.number ?? 0}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>
                <Field>
                  <FieldLabel htmlFor="strategy-name">名称</FieldLabel>
                  <Input
                    id="strategy-name"
                    value={name}
                    disabled={selected !== "new"}
                    onChange={(event) => setName(event.target.value)}
                    required
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="strategy-description">说明</FieldLabel>
                  <Input
                    id="strategy-description"
                    value={description}
                    disabled={selected !== "new"}
                    onChange={(event) => setDescription(event.target.value)}
                  />
                  <FieldDescription>说明选股逻辑、使用的因子和信号含义。</FieldDescription>
                </Field>
              </FieldGroup>
              <div className="flex flex-wrap gap-2">
                {templates.data?.map((template) => (
                  <Button
                    key={template.key}
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setSource(template.source_code)
                      if (selected === "new" && !name) setName(template.name)
                    }}
                  >
                    使用{template.name}
                  </Button>
                ))}
              </div>
              <StrategyEditor value={source} onChange={setSource} />
              {message && (
                <Alert>
                  <AlertTitle>策略状态</AlertTitle>
                  <AlertDescription>{message}</AlertDescription>
                </Alert>
              )}
            </CardContent>
            <CardFooter className="flex gap-2">
              <Button disabled={save.isPending || !name.trim()} onClick={() => save.mutate()}>
                {save.isPending
                  ? "保存中…"
                  : selected === "new"
                    ? "验证并创建策略"
                    : "验证并保存新版本"}
              </Button>
              <div className="flex flex-wrap items-end gap-2">
                <Field>
                  <FieldLabel htmlFor="strategy-run-day">快速测试交易日</FieldLabel>
                  <Input
                    id="strategy-run-day"
                    type="date"
                    value={tradingDay}
                    onChange={(event) => setTradingDay(event.target.value)}
                  />
                  <FieldDescription>
                    快测读取该日及此前 120 个自然日的行情；更长历史请使用回测。
                  </FieldDescription>
                </Field>
                <Button
                  variant="outline"
                  disabled={selected === "new" || !tradingDay}
                  onClick={async () => {
                    try {
                      if (selected === "new") return
                      const queued = await runStrategy(selected, tradingDay, { quantity: 100 })
                      setResult(queued)
                      setMessage(`快速测试任务 ${queued.id} 已进入队列`)
                      setTab("result")
                      await runs.refetch()
                    } catch (error) {
                      setMessage(error instanceof Error ? error.message : "无法创建快速测试任务")
                    }
                  }}
                >
                  运行当前版本
                </Button>
              </div>
            </CardFooter>
          </Card>
        </TabsContent>
        <TabsContent value="result">
          <Card>
            <CardHeader>
              <CardTitle>运行输出</CardTitle>
              <CardDescription>运行只生成信号，不会执行真实交易。</CardDescription>
            </CardHeader>
            <CardContent>
              {runs.error && (
                <Alert variant="destructive">
                  <AlertTitle>无法加载运行记录</AlertTitle>
                  <AlertDescription>{runs.error.message}</AlertDescription>
                </Alert>
              )}
              {runs.data && runs.data.length > 1 && (
                <div className="mb-4 flex flex-wrap gap-2">
                  {runs.data.slice(0, 10).map((run) => (
                    <Button key={run.id} size="sm" variant="outline" onClick={() => setResult(run)}>
                      {run.trading_day} · {localizedLabel(run.status)}
                    </Button>
                  ))}
                </div>
              )}
              {visibleRun ? (
                <div className="flex flex-col gap-3">
                  <Badge variant={visibleRun.status === "failed" ? "destructive" : "secondary"}>
                    {localizedLabel(visibleRun.status)}
                  </Badge>
                  {visibleRun.error && (
                    <Alert variant="destructive">
                      <AlertTitle>运行失败</AlertTitle>
                      <AlertDescription>{visibleRun.error}</AlertDescription>
                    </Alert>
                  )}
                  <p className="text-sm text-muted-foreground">
                    交易日 {visibleRun.trading_day} · 任务 {visibleRun.id}
                  </p>
                  {visibleRun.phase_results.map((phase) => (
                    <div className="flex flex-col gap-2" key={phase.phase}>
                      <h3 className="font-medium">{localizedLabel(phase.phase)}</h3>
                      <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                        {JSON.stringify(phase.signals, null, 2)}
                      </pre>
                      {phase.stdout && <pre>{phase.stdout}</pre>}
                    </div>
                  ))}
                  {visibleRun.status === "queued" && (
                    <p className="text-muted-foreground">等待 worker 领取，页面会自动刷新结果。</p>
                  )}
                  {visibleRun.status === "running" && (
                    <p className="text-muted-foreground">worker 正在处理，页面会自动刷新结果。</p>
                  )}
                </div>
              ) : (
                <p className="text-muted-foreground">尚未运行策略。</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
