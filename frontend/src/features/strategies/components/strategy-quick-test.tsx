import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Play, RefreshCw } from "lucide-react"
import { useState } from "react"

import { CodePreview } from "@/components/code-preview"
import { DatePicker } from "@/components/date-picker"
import { IconButton } from "@/components/icon-button"
import { RunTimingPanel } from "@/components/run-timing"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Switch } from "@/components/ui/switch"
import { localizedLabel } from "@/lib/labels"

import { getQuickTest, quickTestEditor } from "../api"
import type { WorkspaceStrategy } from "../types"

export function StrategyQuickTest({
  source,
  strategy,
  showCodePreview = true,
}: {
  source: string
  showCodePreview?: boolean
  strategy?: WorkspaceStrategy
}) {
  const [day, setDay] = useState("")
  const [allowMock, setAllowMock] = useState(true)
  const [jobId, setJobId] = useState("")
  const client = useQueryClient()
  const query = useQuery({
    queryKey: ["quick-test", jobId],
    queryFn: () => getQuickTest(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (result) =>
      ["queued", "running"].includes(result.state.data?.status ?? "") ? 1000 : false,
  })
  const run = useMutation({
    mutationFn: () =>
      quickTestEditor({
        source_code: source,
        trading_day: day,
        allow_mock: allowMock,
        ...(strategy ? { strategy_id: strategy.id, strategy_version_id: strategy.version_id } : {}),
      }),
    onSuccess: (result) => {
      client.setQueryData(["quick-test", result.id], result)
      setJobId(result.id)
    },
  })
  const result = query.data
  const busy = run.isPending || ["queued", "running"].includes(result?.status ?? "")
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>快速测试</CardTitle>
        <CardDescription>
          运行当前代码，无需先保存，不保存代码快照，也不改变策略状态。结果不能作为实盘启动依据。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex min-w-0 flex-col gap-4">
        {showCodePreview && <CodePreview value={source} label="预览当前测试代码" />}
        <Field>
          <FieldLabel htmlFor="strategy-run-day">快速测试交易日</FieldLabel>
          <div className="flex min-w-0 items-center gap-2">
            <div className="min-w-0 flex-1">
              <DatePicker id="strategy-run-day" value={day} onValueChange={setDay} />
            </div>
            <IconButton
              icon={Play}
              label="运行快速测试"
              disabled={busy || !day || !source.trim()}
              onClick={() => run.mutate()}
            />
          </div>
          <FieldDescription>
            仅模拟所选交易日。盘中报价使用开收盘均值，包含收盘信息。
          </FieldDescription>
        </Field>
        <Field orientation="horizontal">
          <Switch id="quick-test-mock" checked={allowMock} onCheckedChange={setAllowMock} />
          <FieldLabel htmlFor="quick-test-mock">允许 Mock 补足技术指标历史</FieldLabel>
        </Field>
        <p className="text-xs text-muted-foreground">
          默认允许 Mock 补足技术窗口，不补造财报。快速测试最多读取 7 个交易日（含所选日），
          HISTORY_TRADING_DAYS 不会扩大快测窗口。正式回测与实盘使用真实数据。
        </p>
        {(run.error || query.error) && (
          <Alert variant="destructive">
            <AlertTitle>快速测试未完成</AlertTitle>
            <AlertDescription>{(run.error ?? query.error)?.message}</AlertDescription>
            {query.error && (
              <IconButton
                icon={RefreshCw}
                label="重试加载快测结果"
                onClick={() => void query.refetch()}
              />
            )}
          </Alert>
        )}
        {result && (
          <section aria-label="快速测试结果" className="flex min-w-0 flex-col gap-3">
            <div>
              <Badge variant={result.status === "failed" ? "destructive" : "secondary"}>
                {localizedLabel(result.status)}
              </Badge>
            </div>
            {busy && <p role="status">任务正在排队或执行，结果会自动刷新。</p>}
            {result.error && (
              <Alert variant="destructive">
                <AlertTitle>运行失败</AlertTitle>
                <AlertDescription>{result.error}</AlertDescription>
              </Alert>
            )}
            {result.allow_mock && (
              <Badge variant="outline">
                Mock 模式 · 补值{" "}
                {result.mock_usage?.reduce((total, row) => total + row.count, 0) ?? 0} 条
              </Badge>
            )}
            {result.portfolio && (
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                模拟组合：{JSON.stringify(result.portfolio, null, 2)}
              </pre>
            )}
            <RunTimingPanel timing={result.timing} />
            {result.phase_results.map((phase) => (
              <div key={phase.phase} className="flex min-w-0 flex-col gap-2">
                <h3 className="font-medium">{localizedLabel(phase.phase)}</h3>
                <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                  {JSON.stringify(phase.signals, null, 2)}
                </pre>
                {phase.stdout && <pre className="overflow-x-auto text-xs">{phase.stdout}</pre>}
              </div>
            ))}
          </section>
        )}
      </CardContent>
    </Card>
  )
}
