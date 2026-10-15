import { useQuery } from "@tanstack/react-query"
import { ChartNoAxesCombined, CheckCheck, Clock3, Plus } from "lucide-react"
import { Link } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { MetricCard } from "@/components/metric-card"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { listBacktests } from "../api"
import { BacktestTable } from "../components/backtest-table"

export function BacktestListPage() {
  const query = useQuery({ queryKey: ["backtests"], queryFn: listBacktests })
  if (query.isLoading) return <LoadingState label="正在加载回测记录" />
  if (query.error) return <ErrorState title="无法加载回测记录" message={query.error.message} />
  const runs = query.data ?? []
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="回测研究"
        description="验证策略的历史表现，追溯每一次模拟的输入与结果。"
        actions={
          <Button asChild>
            <Link to="/backtests/new">
              <Plus data-icon="inline-start" />
              创建回测
            </Link>
          </Button>
        }
      />
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard
          label="全部回测"
          value={runs.length}
          icon={ChartNoAxesCombined}
          description="按策略版本独立保存"
        />
        <MetricCard
          label="已完成"
          value={runs.filter((run) => run.status === "succeeded").length}
          icon={CheckCheck}
          description="可查看指标、曲线与交易"
        />
        <MetricCard
          label="等待与运行中"
          value={
            runs.filter((run) =>
              ["pending", "queued", "snapshotting", "running"].includes(run.status),
            ).length
          }
          icon={Clock3}
          description="进入详情查看执行进度"
        />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>回测记录</CardTitle>
          <CardDescription>历史结果按策略版本和数据快照保存，不代表未来收益。</CardDescription>
        </CardHeader>
        <CardContent>
          <BacktestTable runs={runs} />
        </CardContent>
      </Card>
    </div>
  )
}
