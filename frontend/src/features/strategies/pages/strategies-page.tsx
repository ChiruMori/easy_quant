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
  if (strategies.isLoading || templates.isLoading)
    return <LoadingState label="正在加载策略工作台" />
  if (strategies.error || templates.error)
    return (
      <ErrorState
        title="无法加载策略"
        message={(strategies.error ?? templates.error)?.message ?? "未知错误"}
      />
    )
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
      <Tabs defaultValue="editor">
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
              <Button
                variant="outline"
                disabled={selected === "new"}
                onClick={async () => {
                  if (selected !== "new") setResult(await runStrategy(selected, { quantity: 100 }))
                }}
              >
                运行当前版本
              </Button>
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
              {result ? (
                <div className="flex flex-col gap-3">
                  <Badge variant={result.status === "succeeded" ? "secondary" : "destructive"}>
                    {localizedLabel(result.status)}
                  </Badge>
                  {result.error && (
                    <Alert variant="destructive">
                      <AlertTitle>运行失败</AlertTitle>
                      <AlertDescription>{result.error}</AlertDescription>
                    </Alert>
                  )}
                  <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                    {JSON.stringify(result.signals, null, 2)}
                  </pre>
                  {result.stdout && <pre>{result.stdout}</pre>}
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
