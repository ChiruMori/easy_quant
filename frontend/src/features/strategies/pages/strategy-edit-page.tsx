import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, ChartNoAxesCombined, ChevronDown, Eye, FileCode2, Save } from "lucide-react"
import { useRef, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { ConfirmAction } from "@/components/confirm-action"
import { IconButton, IconLink } from "@/components/icon-button"
import { PageHeader } from "@/components/page-header"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

import {
  createStrategy,
  getStrategyVersion,
  listStrategyTemplates,
  saveStrategyDraft,
  versionPath,
} from "../api"
import { StrategyEditor } from "../components/strategy-editor"
import { StrategyLibrarySidebar } from "../components/strategy-library-sidebar"
import { StrategyQuickTest } from "../components/strategy-quick-test"
import type { StrategyTemplate, WorkspaceStrategy } from "../types"
import { StrategyDetailContent } from "./strategy-detail-page"

export const BLANK_STRATEGY = `def before_market(context, parameters):
    return []


def on_market(context, parameters):
    return []


def after_market(context, parameters):
    return []
`

export function StrategyEditPage() {
  const { strategyId = "", versionId = "" } = useParams()
  const query = useQuery({
    queryKey: ["strategy-version", strategyId, versionId],
    queryFn: () => getStrategyVersion(strategyId, versionId),
    enabled: Boolean(strategyId && versionId),
    staleTime: 0,
  })
  if (!strategyId) return <StrategyDraftForm key="new" />
  if (query.isLoading) return <LoadingState label="正在加载策略草稿" />
  if (query.error || !query.data)
    return (
      <ErrorState title="无法加载策略草稿" message={query.error?.message ?? "策略版本不存在"} />
    )
  if (query.data.state !== "draft") return <StrategyDetailContent strategy={query.data} locked />
  return <StrategyDraftForm key={query.data.version_id} strategy={query.data} />
}

function StrategyDraftForm({ strategy }: { strategy?: WorkspaceStrategy }) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [name, setName] = useState(strategy?.name ?? "")
  const [description, setDescription] = useState(strategy?.description ?? "")
  const [source, setSource] = useState(strategy?.source_code ?? BLANK_STRATEGY)
  const [revision, setRevision] = useState(strategy?.revision ?? 0)
  const [message, setMessage] = useState(params.has("saved") ? "草稿已保存" : "")
  const [template, setTemplate] = useState<StrategyTemplate>()
  const saving = useRef(false)
  const createdDraft = useRef<{ id: string; versionId: string } | undefined>(undefined)
  const templates = useQuery({ queryKey: ["strategy-templates"], queryFn: listStrategyTemplates })
  const save = useMutation<WorkspaceStrategy, Error, boolean>({
    mutationFn: async () => {
      if (strategy)
        return saveStrategyDraft(strategy.id, strategy.version_id, {
          name: name.trim(),
          description,
          source_code: source,
          expected_revision: revision,
        })
      if (createdDraft.current) {
        const created = createdDraft.current
        const saved = await getStrategyVersion(created.id, created.versionId)
        return saveStrategyDraft(created.id, created.versionId, {
          name: name.trim(),
          description,
          source_code: source,
          expected_revision: saved.revision,
        })
      }
      const created = await createStrategy({ name: name.trim(), description, source_code: source })
      createdDraft.current = { id: created.id, versionId: created.current_version_id }
      return getStrategyVersion(created.id, created.current_version_id)
    },
    onSuccess: async (updated, goToBacktest) => {
      setRevision(updated.revision)
      setName(updated.name)
      setMessage("草稿已保存")
      client.setQueryData(["strategy-version", updated.id, updated.version_id], updated)
      await client.invalidateQueries({ queryKey: ["strategies"] })
      if (goToBacktest) navigate(`/backtests/new?version=${updated.version_id}`)
      else if (!strategy)
        navigate(`${versionPath(updated.id, updated.version_id)}/edit?saved=1`, { replace: true })
    },
  })
  async function submit(goToBacktest = false) {
    if (saving.current || !name.trim()) return
    saving.current = true
    try {
      await save.mutateAsync(goToBacktest)
    } catch {
      // useMutation 保留保存错误；留在编辑页重试。
    } finally {
      saving.current = false
    }
  }
  const availableTemplates = [
    { key: "blank", name: "空白模板", source_code: BLANK_STRATEGY },
    ...(templates.data ?? []),
  ]
  return (
    <div className="flex min-w-0 flex-col gap-5">
      <PageHeader
        title={strategy ? `编辑 ${strategy.name} · v${strategy.number}` : "新建策略"}
        description="草稿可直接保存；提交回测后锁定，继续编辑将创建新的草稿版本。"
        actions={
          <>
            <IconLink icon={ArrowLeft} label="返回策略列表" to="/strategies" />
            {strategy && (
              <IconLink
                icon={Eye}
                label="查看策略详情"
                to={versionPath(strategy.id, strategy.version_id)}
              />
            )}
            <IconButton
              icon={Save}
              variant="default"
              label={strategy ? "保存草稿" : "创建策略"}
              type="submit"
              form="strategy-draft-form"
              disabled={save.isPending || !name.trim()}
            />
            <IconButton
              icon={ChartNoAxesCombined}
              label="保存并回测"
              disabled={save.isPending || !name.trim()}
              onClick={() => void submit(true)}
            />
          </>
        }
      />
      <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <section aria-label="策略编辑区" className="flex min-w-0 flex-col gap-5">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>策略草稿</CardTitle>
              <CardDescription>
                保存仅更新当前草稿，不新增版本。代码在受限子进程中执行，不会自动下单。
              </CardDescription>
            </CardHeader>
            <CardContent className="flex min-w-0 flex-col gap-4">
              <form
                id="strategy-draft-form"
                onSubmit={(event) => {
                  event.preventDefault()
                  void submit()
                }}
              >
                <FieldGroup className="sm:grid sm:grid-cols-2">
                  <Field>
                    <FieldLabel htmlFor="strategy-name">名称</FieldLabel>
                    <Input
                      id="strategy-name"
                      value={name}
                      maxLength={160}
                      onChange={(event) => {
                        setName(event.target.value)
                        setMessage("")
                      }}
                      required
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="strategy-description">说明</FieldLabel>
                    <Input
                      id="strategy-description"
                      value={description}
                      onChange={(event) => {
                        setDescription(event.target.value)
                        setMessage("")
                      }}
                    />
                    <FieldDescription>说明选股逻辑、因子和信号含义。</FieldDescription>
                  </Field>
                </FieldGroup>
              </form>
              <div className="flex flex-wrap items-center gap-2">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" type="button" disabled={save.isPending}>
                      <FileCode2 data-icon="inline-start" />
                      代码模板
                      <ChevronDown data-icon="inline-end" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    <DropdownMenuGroup>
                      {availableTemplates.map((item) => (
                        <DropdownMenuItem key={item.key} onSelect={() => setTemplate(item)}>
                          使用{item.name}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
                {templates.isLoading && (
                  <span role="status" className="text-sm text-muted-foreground">
                    正在加载示例…
                  </span>
                )}
              </div>
              {templates.error && (
                <Alert variant="destructive">
                  <AlertTitle>无法加载示例模板</AlertTitle>
                  <AlertDescription>{templates.error.message}，空白模板仍可使用。</AlertDescription>
                </Alert>
              )}
              <StrategyEditor
                value={source}
                onChange={(value) => {
                  setSource(value)
                  setMessage("")
                }}
              />
              {save.error && (
                <Alert variant="destructive">
                  <AlertTitle>草稿未保存</AlertTitle>
                  <AlertDescription>{save.error.message}</AlertDescription>
                </Alert>
              )}
              {message && (
                <p role="status" className="text-sm">
                  {message}
                </p>
              )}
              {save.isPending && <p role="status">正在验证并保存草稿…</p>}
            </CardContent>
          </Card>
          <StrategyQuickTest source={source} strategy={strategy} showCodePreview={false} />
        </section>
        <StrategyLibrarySidebar />
      </div>
      <ConfirmAction
        open={Boolean(template)}
        onOpenChange={(open) => {
          if (!open) setTemplate(undefined)
        }}
        label="替换模板"
        title="替换当前编辑器内容？"
        description={`确认后使用“${template?.name ?? ""}”覆盖当前编辑器的全部代码，未保存的修改将丢失。`}
        action={async () => {
          if (template) {
            setSource(template.source_code)
            setMessage("")
          }
        }}
      />
    </div>
  )
}
