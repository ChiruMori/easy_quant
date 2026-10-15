import { useQuery } from "@tanstack/react-query"
import { Activity, ArrowRight, ChartNoAxesCombined, FlaskConical, Plus } from "lucide-react"
import { Link } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { MetricCard } from "@/components/metric-card"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { listBacktests } from "@/features/backtests/api"
import { BacktestTable } from "@/features/backtests/components/backtest-table"
import { listLive } from "@/features/live-tracking/api"
import { listStrategies } from "@/features/strategies/api"

const workflow = [
  {
    to: "/strategies",
    title: "构建策略",
    description: "选择因子，编辑并保存策略版本。",
    icon: FlaskConical,
  },
  {
    to: "/backtests/new",
    title: "验证历史表现",
    description: "使用已同步行情运行日线回测。",
    icon: ChartNoAxesCombined,
  },
  {
    to: "/live",
    title: "跟踪实际操作",
    description: "查看建议，按真实成交确认账本。",
    icon: Activity,
  },
]

export function DashboardPage() {
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: listStrategies })
  const backtests = useQuery({ queryKey: ["backtests"], queryFn: listBacktests })
  const live = useQuery({ queryKey: ["live-instances"], queryFn: listLive })
  const error = strategies.error ?? backtests.error ?? live.error
  if (error)
    return (
      <div className="flex flex-col items-start gap-4">
        <ErrorState title="无法加载工作台" message={error.message} />
        <Button
          variant="outline"
          onClick={() => {
            void strategies.refetch()
            void backtests.refetch()
            void live.refetch()
          }}
        >
          重新加载
        </Button>
      </div>
    )
  if (!strategies.isSuccess || !backtests.isSuccess || !live.isSuccess)
    return <LoadingState label="正在加载工作台概览" />
  const completed = backtests.data.filter((run) => run.status === "succeeded").length
  const active = live.data.filter((instance) => instance.status === "active").length
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="研究概览"
        description="从策略研究到实际跟踪，掌握当前工作进展。"
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
          label="已保存策略"
          value={strategies.data.length}
          description="每次保存保留不可变版本"
          icon={FlaskConical}
        />
        <MetricCard
          label="回测记录"
          value={backtests.data.length}
          description={`${completed} 次已完成 · 可查看独立结果`}
          icon={ChartNoAxesCombined}
        />
        <MetricCard
          label="运行中的实盘"
          value={active}
          description={`共 ${live.data.length} 个实例 · 由你确认实际操作`}
          icon={Activity}
        />
      </div>
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
        <Card>
          <CardHeader className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>回测速览</CardTitle>
              <CardDescription>查看策略版本对应的指标与模拟交易。</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/backtests">
                全部记录
                <ArrowRight data-icon="inline-end" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            <BacktestTable runs={backtests.data.slice(0, 5)} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>研究流程</CardTitle>
            <CardDescription>逐步验证，再跟踪实际表现。</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            {workflow.map(({ to, title, description, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className="group flex items-start gap-3 rounded-md outline-offset-4"
              >
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                  <Icon className="size-4" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-sm font-medium group-hover:text-primary">{title}</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>
      <p className="text-xs leading-5 text-muted-foreground">
        回测为历史模拟，不代表未来收益。实盘跟踪仅生成建议，实际操作由你确认。
      </p>
    </div>
  )
}
