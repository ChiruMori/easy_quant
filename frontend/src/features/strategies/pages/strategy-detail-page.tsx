import { useQuery } from "@tanstack/react-query"
import { ArrowLeft, ChartNoAxesCombined } from "lucide-react"
import { Link, useNavigate, useParams } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { CodeWorkspace } from "@/components/code-workspace"
import { DeleteResourceButton } from "@/components/delete-resource-button"
import { IconLink } from "@/components/icon-button"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { getStrategyVersion, versionPath } from "../api"
import { EditStrategyAction, strategyStateLabel } from "../components/strategy-actions"
import { StrategyQuickTest } from "../components/strategy-quick-test"
import type { WorkspaceStrategy } from "../types"

export function StrategyDetailPage() {
  const { strategyId = "", versionId = "" } = useParams()
  const query = useQuery({
    queryKey: ["strategy-version", strategyId, versionId],
    queryFn: () => getStrategyVersion(strategyId, versionId),
    staleTime: 0,
  })
  if (query.isLoading) return <LoadingState label="正在加载策略版本" />
  if (query.error || !query.data)
    return (
      <ErrorState title="无法加载策略版本" message={query.error?.message ?? "策略版本不存在"} />
    )
  return <StrategyDetailContent strategy={query.data} />
}

export function StrategyDetailContent({
  strategy,
  locked = false,
}: {
  strategy: WorkspaceStrategy
  locked?: boolean
}) {
  const navigate = useNavigate()
  return (
    <div className="flex min-w-0 flex-col gap-5">
      <PageHeader
        title={`${strategy.name} · v${strategy.number}`}
        description={
          locked
            ? "此版本已锁定。编辑需要确认创建新的草稿版本。"
            : "查看策略代码、生命周期与关联实盘。"
        }
        actions={
          <>
            <IconLink icon={ArrowLeft} label="返回策略列表" to="/strategies" />
            <EditStrategyAction strategy={strategy} />
            <IconLink
              icon={ChartNoAxesCombined}
              label="使用此版本回测"
              to={`/backtests/new?version=${strategy.version_id}`}
            />
          </>
        }
      />
      <Card>
        <CardHeader>
          <CardTitle>版本信息</CardTitle>
          <CardDescription>{strategy.description || "暂无说明"}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div>
            <Badge variant={strategy.state === "live" ? "success" : "secondary"}>
              {strategyStateLabel[strategy.state]}
            </Badge>
          </div>
          <p className="text-sm">
            创建时间：
            {new Date(strategy.created_at).toLocaleString("zh-CN", {
              timeZone: "Asia/Shanghai",
              hour12: false,
            })}
          </p>
          <p className="text-sm">
            关联实盘：
            {strategy.live_instances.length
              ? strategy.live_instances.map((row) => (
                  <Link
                    key={row.id}
                    className="mr-3 inline-flex items-center gap-1 font-medium text-primary hover:opacity-80"
                    to={`/live/${row.id}`}
                  >
                    {row.name}
                  </Link>
                ))
              : "无"}
          </p>
          <div>
            <DeleteResourceButton
              path={versionPath(strategy.id, strategy.version_id)}
              label="删除策略"
              description="将删除此版本及其关联测试数据。关联实盘存在时不可删除。"
              onDeleted={() => navigate("/strategies")}
            />
          </div>
        </CardContent>
      </Card>
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>策略代码</CardTitle>
          <CardDescription>只读预览；使用编辑按钮修改草稿或创建新版本。</CardDescription>
        </CardHeader>
        <CardContent>
          <CodeWorkspace value={strategy.source_code ?? ""} />
        </CardContent>
      </Card>
      <StrategyQuickTest strategy={strategy} source={strategy.source_code ?? ""} />
    </div>
  )
}
